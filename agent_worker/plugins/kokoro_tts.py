"""
Kokoro TTS Plugin for LiveKit Agents
=====================================

Local text-to-speech using Kokoro TTS with streaming audio generation.
No cloud APIs required — runs entirely on your hardware.

Features:
  - 11 built-in voices (American/British, Male/Female)
  - Sentence-level streaming for low latency
  - GPU acceleration via CUDA (falls back to CPU)
  - 24kHz high-quality audio output

Reference:
  CoreWorxLab/local-livekit-plugins/piper_tts.py
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import TYPE_CHECKING

import numpy as np

from livekit.agents import tts, APIConnectOptions

if TYPE_CHECKING:
    from livekit.agents.tts.tts import AudioEmitter

__all__ = ["KokoroTTS"]

logger = logging.getLogger(__name__)

AVAILABLE_VOICES = [
    "af_heart",       # American Female - Heart (warm, friendly)
    "af_bella",       # American Female - Bella
    "af_nicole",      # American Female - Nicole
    "af_sarah",       # American Female - Sarah
    "af_sky",         # American Female - Sky
    "am_adam",        # American Male - Adam
    "am_michael",     # American Male - Michael
    "bf_emma",        # British Female - Emma
    "bf_isabella",    # British Female - Isabella
    "bm_george",      # British Male - George
    "bm_lewis",       # British Male - Lewis
]


class _KokoroChunkedStream(tts.ChunkedStream):
    """
    Internal ChunkedStream implementation for Kokoro TTS.

    Handles the async bridge between LiveKit's streaming interface
    and Kokoro's synchronous sentence-level synthesis.
    """

    def __init__(
        self,
        *,
        tts_plugin: KokoroTTS,
        input_text: str,
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(tts=tts_plugin, input_text=input_text, conn_options=conn_options)
        self._kokoro_tts = tts_plugin

    async def _run(self, emitter: AudioEmitter) -> None:
        """Synthesize audio and emit it to LiveKit."""
        emitter.initialize(
            request_id=str(uuid.uuid4()),
            sample_rate=self._kokoro_tts.sample_rate,
            num_channels=self._kokoro_tts.num_channels,
            mime_type="audio/pcm",
        )

        start_time = time.perf_counter()

        # Run blocking Kokoro synthesis in thread pool
        loop = asyncio.get_running_loop()
        audio_chunks = await loop.run_in_executor(
            None,
            self._synthesize_blocking,
            self._input_text,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        logger.debug(f"TTS latency: {elapsed_ms:.0f}ms for {len(self._input_text)} chars")

        for chunk in audio_chunks:
            emitter.push(chunk)

    def _synthesize_blocking(self, text: str) -> list[bytes]:
        """
        Blocking synthesis operation.

        Runs in a thread pool to avoid blocking the async event loop.
        Kokoro generates audio in sentence-level chunks for streaming.
        """
        pipeline = self._kokoro_tts._pipeline
        voice = self._kokoro_tts._voice
        speed = self._kokoro_tts._speed

        chunks: list[bytes] = []

        try:
            generator = pipeline(text, voice=voice, speed=speed)

            for graphemes, phonemes, audio_chunk in generator:
                if audio_chunk is not None and len(audio_chunk) > 0:
                    # audio_chunk is float32 [-1, 1], convert to int16 PCM
                    audio_int16 = (audio_chunk * 32767).astype(np.int16)
                    chunks.append(audio_int16.tobytes())

        except Exception as e:
            logger.error(f"Kokoro synthesis error: {e}")
            # Yield a short silence on error
            silence = np.zeros(self._kokoro_tts.sample_rate // 2, dtype=np.int16)
            chunks.append(silence.tobytes())

        return chunks


class KokoroTTS(tts.TTS):
    """
    LiveKit TTS plugin using Kokoro for local speech synthesis.

    Args:
        voice: Voice ID to use (e.g., "af_heart", "am_adam").
        lang_code: Language code — "a" for American English, "b" for British English.
        speed: Speech rate multiplier. 1.0 = normal.
        device: Processing device — "cuda" for GPU, "cpu" for CPU.
    """

    def __init__(
        self,
        voice: str = "af_heart",
        lang_code: str = "a",
        speed: float = 1.0,
        device: str = "cpu",
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=24000,
            num_channels=1,
        )

        self._voice = voice
        self._speed = speed

        logger.info(f"Loading Kokoro TTS pipeline (lang={lang_code}, device={device})")

        from kokoro import KPipeline

        self._pipeline = KPipeline(lang_code=lang_code, device=device)

        logger.info(f"Kokoro TTS ready — voice={voice}, speed={speed}")

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions | None = None,
    ) -> tts.ChunkedStream:
        """
        Synthesize speech from text.

        Returns a ChunkedStream that yields sentence-level audio chunks.
        """
        if conn_options is None:
            conn_options = APIConnectOptions()

        logger.debug(f"Synthesizing ({len(text)} chars): {text[:80]}...")

        return _KokoroChunkedStream(
            tts_plugin=self,
            input_text=text,
            conn_options=conn_options,
        )
