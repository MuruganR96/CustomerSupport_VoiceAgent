"""
LiveKit Agents Worker — Customer Support Voice Agent
=====================================================

This is the main entrypoint for the LiveKit Agents worker process.
It orchestrates:
  - FasterWhisperSTT (in-process speech-to-text)
  - KokoroTTS (in-process text-to-speech)
  - Silero VAD (voice activity detection)
  - LangGraph agent (reasoning + tool calling) via langchain.LLMAdapter

Usage:
  python agent_worker/main.py start
  python agent_worker/main.py dev
"""

import json
import logging
import os

# Fix compatibility: langchain-core >= 0.3.50 changed BaseMessage.text from
# @property to a regular method, but livekit-plugins-langchain accesses it
# as a property (msg.text). Patch it back to a property so the adapter works.
from langchain_core.messages import BaseMessage as _BaseMessage

if not isinstance(getattr(_BaseMessage, "text", None), property):
    _original_text = _BaseMessage.text

    @property
    def _text_prop(self):
        return _original_text(self)

    _BaseMessage.text = _text_prop

from livekit.agents import (
    AgentSession,
    Agent,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
)
from livekit.plugins import silero
from livekit.plugins.langchain import LLMAdapter

from agent_worker.plugins.faster_whisper_stt import FasterWhisperSTT
from agent_worker.plugins.kokoro_tts import KokoroTTS
from agent_worker.agent.graph import create_agent_graph, load_system_prompt

logger = logging.getLogger(__name__)


# ── Pre-warm: load models once per process ───────────────────────────────────

def prewarm(proc: JobProcess):
    """Called when a new worker process starts. Load heavy models here."""
    proc.userdata["stt"] = FasterWhisperSTT(
        model_size=os.getenv("WHISPER_MODEL", "base"),
        device=os.getenv("WHISPER_DEVICE", "cpu"),
        compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        language="en",
        beam_size=5,
        vad_filter=True,
    )

    proc.userdata["tts"] = KokoroTTS(
        voice=os.getenv("KOKORO_VOICE", "af_heart"),
        lang_code=os.getenv("KOKORO_LANG_CODE", "a"),
        speed=float(os.getenv("KOKORO_SPEED", "1.0")),
        device=os.getenv("KOKORO_DEVICE", "cpu"),
    )

    proc.userdata["vad"] = silero.VAD.load()
    proc.userdata["graph"] = create_agent_graph()
    proc.userdata["system_prompt"] = load_system_prompt()

    logger.info("All models loaded — agent worker ready")


# ── Entrypoint ───────────────────────────────────────────────────────────────

async def entrypoint(ctx: JobContext):
    """Called when a new voice session is dispatched to this worker."""
    await ctx.connect()

    stt_instance = ctx.proc.userdata["stt"]
    tts_instance = ctx.proc.userdata["tts"]
    vad_instance = ctx.proc.userdata["vad"]
    compiled_graph = ctx.proc.userdata["graph"]
    system_prompt = ctx.proc.userdata["system_prompt"]

    # Extract metadata from agent dispatch
    metadata = {}
    job_metadata = ctx.job.metadata
    if job_metadata:
        try:
            metadata = json.loads(job_metadata)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Could not parse job metadata: {job_metadata}")

    customer_name = metadata.get("customer_name", "Customer")
    session_id = metadata.get("session_id", ctx.room.name)

    logger.info(
        f"Starting agent for session={session_id}, "
        f"customer={customer_name}, room={ctx.room.name}"
    )

    # Create per-session LLM adapter with thread_id for LangGraph memory
    llm = LLMAdapter(
        graph=compiled_graph,
        config={"configurable": {"thread_id": session_id}},
    )

    agent = Agent(instructions=system_prompt)

    agent_session = AgentSession(
        stt=stt_instance,
        tts=tts_instance,
        llm=llm,
        vad=vad_instance,
    )

    await agent_session.start(agent=agent, room=ctx.room)

    # Generate initial greeting
    await agent_session.generate_reply(
        instructions=f"Greet the customer warmly. Their name is {customer_name}. "
        f"Introduce yourself as Alex, a customer support specialist, and ask how you can help."
    )


# ── CLI entry ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="customer-support",
            initialize_process_timeout=120.0,
            num_idle_processes=0,
            job_memory_warn_mb=3000,
            job_memory_limit_mb=0,
        )
    )
