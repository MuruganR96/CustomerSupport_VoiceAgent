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
    # Look for prompt config relative to this file, then fall back to backend path
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
            "voice_rules": {},
        }

    persona = config.get("persona", {})
    voice_rules = config.get("voice_rules", {})
    support_flow = config.get("support_flow", [])

    flow_text = ""
    for phase in support_flow:
        goals = ", ".join(phase.get("goals", []))
        flow_text += f"- {phase['phase']} ({phase.get('duration', '')}): {goals}\n"

    fillers = ", ".join(voice_rules.get("fillers", []))
    reactions = ", ".join(voice_rules.get("reactions", []))

    return f"""You are {persona.get('name', 'Alex')}, a {persona.get('role', 'Customer Support Specialist')}.
Your style is: {persona.get('style', 'friendly and professional')}.

=== CONVERSATION FLOW ===
{flow_text}

=== CRITICAL VOICE BEHAVIOR ===
This is a VOICE conversation. Your responses will be spoken aloud by a TTS engine.

Response Rules:
- Keep responses SHORT: 1-3 sentences maximum
- Use natural fillers: {fillers}
- Use natural reactions: {reactions}
- NEVER use markdown, bullet points, numbered lists, or special formatting
- NEVER use asterisks, bold, headers, or code blocks
- Write everything as natural spoken language
- If explaining steps, say them conversationally: "First you'll want to... then after that..."
- If you need to mention more than 3 items, summarize instead of listing
- Always check: "Does that help?" or "Is there anything else?"
- If you can't resolve the issue, offer to create a support ticket

Tool Usage:
- Use lookup_order when customer mentions an order number
- Use lookup_account when customer provides their email
- Use check_knowledge_base for general questions about policies
- Use create_ticket when you can't resolve the issue or customer requests escalation
- Use end_call ONLY after confirming the customer has no more questions

IMPORTANT: You are ONLY a customer support agent. Politely redirect any off-topic requests.
Do NOT make up information. If you don't know something, say so and offer to check or escalate."""


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
