"""
LiveKit Agents Worker — Customer Support Voice Agent
=====================================================

This is the main entrypoint for the LiveKit Agents worker process.
It orchestrates:
  - FasterWhisperSTT (in-process speech-to-text)
  - KokoroTTS (in-process text-to-speech)
  - Silero VAD (voice activity detection)
  - LangGraph agent (reasoning + tool calling) via langchain.LLM adapter

Usage:
  python -m livekit.agents.cli start --agent agent_worker.main
  python -m livekit.agents.cli dev --agent agent_worker.main
"""

import json
import logging
import os

from livekit.agents import AgentSession, Agent, cli, RtcSession
from livekit.plugins import silero, langchain

from agent_worker.plugins.faster_whisper_stt import FasterWhisperSTT
from agent_worker.plugins.kokoro_tts import KokoroTTS
from agent_worker.agent.graph import create_agent_graph, load_system_prompt

logger = logging.getLogger(__name__)

# ── Pre-load models at worker startup (shared across sessions) ───────────────

stt_instance = FasterWhisperSTT(
    model_size=os.getenv("WHISPER_MODEL", "base"),
    device=os.getenv("WHISPER_DEVICE", "cpu"),
    compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
    language="en",
    beam_size=5,
    vad_filter=True,
)

tts_instance = KokoroTTS(
    voice=os.getenv("KOKORO_VOICE", "af_heart"),
    lang_code=os.getenv("KOKORO_LANG_CODE", "a"),
    speed=float(os.getenv("KOKORO_SPEED", "1.0")),
    device=os.getenv("KOKORO_DEVICE", "cpu"),
)

vad_instance = silero.VAD.load()

compiled_graph = create_agent_graph()

system_prompt = load_system_prompt()

logger.info("All models loaded — agent worker ready")


# ── Agent Definition ─────────────────────────────────────────────────────────

class CustomerSupportAgent(Agent):
    """Customer support agent powered by LangGraph."""

    def __init__(self, *, customer_name: str = "Customer"):
        super().__init__(instructions=system_prompt)
        self._customer_name = customer_name


# ── Entrypoint ───────────────────────────────────────────────────────────────

@cli.main
async def entrypoint(session: RtcSession):
    """Called when a new voice session is dispatched to this worker."""
    room = session.room

    # Extract metadata from agent dispatch
    metadata = {}
    if session.metadata:
        try:
            metadata = json.loads(session.metadata)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Could not parse session metadata: {session.metadata}")

    customer_name = metadata.get("customer_name", "Customer")
    session_id = metadata.get("session_id", room.name)

    logger.info(f"Starting agent for session={session_id}, customer={customer_name}, room={room.name}")

    # Create per-session LLM adapter with thread_id for LangGraph memory
    llm = langchain.LLM(
        graph=compiled_graph,
        config={"configurable": {"thread_id": session_id}},
    )

    agent = CustomerSupportAgent(customer_name=customer_name)

    agent_session = AgentSession(
        stt=stt_instance,
        tts=tts_instance,
        llm=llm,
        vad=vad_instance,
    )

    await agent_session.start(room=room, agent=agent)

    # Generate initial greeting
    await agent_session.generate_reply(
        instructions=f"Greet the customer warmly. Their name is {customer_name}. "
        f"Introduce yourself as Alex, a customer support specialist, and ask how you can help."
    )
