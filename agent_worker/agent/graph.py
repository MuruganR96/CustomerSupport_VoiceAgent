"""LangGraph customer support agent with tool calling.

This graph is used with the LiveKit Agents langchain.LLM adapter
to power the voice agent's reasoning and tool-calling capabilities.
"""

import logging
import yaml
from pathlib import Path
from typing import Annotated, TypedDict, Sequence

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from .tools import support_tools

logger = logging.getLogger(__name__)


# ── State Definition ──────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """State schema for the customer support agent graph."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    call_ended: bool
    session_id: str


# ── Prompt Loading ────────────────────────────────────────────────────────────

def load_system_prompt() -> str:
    """Load and format the system prompt from YAML config."""
    prompt_paths = [
        Path(__file__).parent.parent / "config" / "prompts" / "customer_support_prompt.yaml",
        Path(__file__).parent.parent.parent / "backend" / "config" / "prompts" / "customer_support_prompt.yaml",
    ]

    config = None
    for prompt_path in prompt_paths:
        try:
            with open(prompt_path, "r") as f:
                config = yaml.safe_load(f)
            break
        except FileNotFoundError:
            continue

    if config is None:
        logger.warning("Prompt config not found, using default")
        config = {
            "persona": {"name": "Alex", "role": "Customer Support Specialist"},
        }

    persona = config.get("persona", {})
    voice_rules = config.get("voice_output_rules", {})
    speech = config.get("speech_patterns", {})
    support_flow = config.get("support_flow", [])
    guardrails = config.get("guardrails", [])

    name = persona.get("name", "Alex")
    role = persona.get("role", "Customer Support Specialist")

    # Build personality paragraph
    personality_lines = persona.get("personality", [])
    personality_text = " ".join(personality_lines)

    # Build formatting rules
    formatting = voice_rules.get("formatting", {})
    formatting_text = "\n".join(f"- {k.title()}: {v}" for k, v in formatting.items())

    # Build grammar rules
    grammar_rules = "\n".join(f"- {r}" for r in speech.get("grammar", []))

    # Build filler examples
    fillers = speech.get("fillers", {})
    filler_text = ""
    for category, examples in fillers.items():
        filler_text += f"- {category.title()}: {', '.join(examples)}\n"

    # Build reaction examples
    reactions = speech.get("reactions", {})
    reaction_text = ""
    for category, examples in reactions.items():
        reaction_text += f"- {category.title()}: {', '.join(examples)}\n"

    # Build pacing rules
    pacing_text = "\n".join(f"- {r}" for r in speech.get("pacing", []))

    # Build conversation flow with examples
    flow_text = ""
    for phase in support_flow:
        goals = ", ".join(phase.get("goals", []))
        example = phase.get("example", "")
        flow_text += f"- {phase['phase']}: {goals}\n"
        if example:
            flow_text += f'  Example: "{example}"\n'

    # Build formatting bans
    never_use = voice_rules.get("never_use", [])
    bans_text = "\n".join(f"- NEVER use {item}" for item in never_use)

    # Build guardrails
    guardrails_text = "\n".join(f"- {g}" for g in guardrails)

    return f"""You are {name}, a {role}.

IMPORTANT: Respond in plain text only. No markdown. No formatting. This is a voice conversation.

=== WHO YOU ARE ===
{personality_text}

=== VOICE OUTPUT RULES ===
This is a VOICE conversation. Your responses will be spoken aloud by a TTS engine.
Keep responses SHORT: one to three sentences maximum.

{bans_text}

Write everything as natural spoken language. If explaining steps, say them conversationally: \
"First you'll wanna... then after that..."
If you need to mention more than three items, summarize instead of listing them out.

=== TTS FORMATTING ===
{formatting_text}

=== HOW YOU TALK ===
Speech patterns — follow these closely:
{grammar_rules}

Natural fillers to use:
{filler_text}
Reactions to use:
{reaction_text}
Pacing:
{pacing_text}

=== CONVERSATION FLOW ===
{flow_text}

=== TOOLS ===
- Use lookup_order when the customer mentions an order number
- Use lookup_account when they provide their email
- Use check_knowledge_base for general questions about policies or how things work
- Use create_ticket when you can't resolve the issue or the customer wants escalation
- Use end_call ONLY after confirming the customer has no more questions

=== GUARDRAILS ===
{guardrails_text}

REMEMBER: You are speaking out loud. Plain text only. No markdown, no bullet points, no formatting. \
Keep it short and conversational. One to three sentences max, then check in."""


# ── Graph Nodes ───────────────────────────────────────────────────────────────

def create_agent_graph(model_name: str = "gpt-4o-mini", temperature: float = 0.7):
    """Build the LangGraph customer support agent.

    Returns a compiled graph suitable for use with langchain.LLM adapter.
    """

    # LLM with tools bound
    llm = ChatOpenAI(model=model_name, temperature=temperature)
    llm_with_tools = llm.bind_tools(support_tools)

    system_prompt = load_system_prompt()

    # --- Agent node: decides what to do ---
    def agent_node(state: AgentState) -> dict:
        """Main agent reasoning node."""
        messages = list(state["messages"])

        # Ensure system prompt is first message
        if not messages or not isinstance(messages[0], SystemMessage):
            messages.insert(0, SystemMessage(content=system_prompt))

        response = llm_with_tools.invoke(messages)

        # Check if end_call tool was invoked
        call_ended = False
        if response.tool_calls:
            for tc in response.tool_calls:
                if tc["name"] == "end_call":
                    call_ended = True

        return {"messages": [response], "call_ended": call_ended}

    # --- Router: should we use tools or respond? ---
    def should_continue(state: AgentState) -> str:
        """Route based on whether the agent wants to call tools."""
        last_message = state["messages"][-1]

        if state.get("call_ended", False):
            return "end"

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"

        return "end"

    # --- Build the graph ---
    tool_node = ToolNode(support_tools)

    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    # Set entry point
    graph.set_entry_point("agent")

    # Add conditional edges
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END,
        },
    )

    # Tools always go back to agent
    graph.add_edge("tools", "agent")

    # Compile with checkpointing for conversation memory
    memory = MemorySaver()
    compiled = graph.compile(checkpointer=memory)

    return compiled
