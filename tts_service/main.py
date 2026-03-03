"""Kokoro TTS Streaming Service.

In-house Text-to-Speech microservice wrapping Kokoro TTS.
Exposes a simple HTTP API:
  POST /synthesize — streaming synthesis, returns PCM audio chunks
  POST /synthesize/wav — returns complete WAV file
  GET  /voices — list available voices
  GET  /health — health check
  WS   /ws/synthesize — WebSocket streaming synthesis
"""

import io
import os
import wave
import struct
import logging
import asyncio
from typing import Optional, AsyncGenerator

import numpy as np
import torch
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

KOKORO_VOICE = os.getenv("KOKORO_VOICE", "af_heart")
KOKORO_SAMPLE_RATE = int(os.getenv("KOKORO_SAMPLE_RATE", "24000"))
KOKORO_DEVICE = os.getenv("KOKORO_DEVICE", "cpu")
KOKORO_LANG_CODE = os.getenv("KOKORO_LANG_CODE", "a")  # 'a' for American English

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Kokoro TTS Service", version="1.0.0")

# Global model reference
pipeline = None

# Available voices (Kokoro v0.19+)
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


@app.on_event("startup")
async def load_model():
    """Load the Kokoro TTS model on startup."""
    global pipeline
    try:
        from kokoro import KPipeline

        logger.info(f"Loading Kokoro TTS pipeline (lang={KOKORO_LANG_CODE}, device={KOKORO_DEVICE})")
        pipeline = KPipeline(lang_code=KOKORO_LANG_CODE, device=KOKORO_DEVICE)
        logger.info("Kokoro TTS pipeline loaded successfully")
    except ImportError:
        logger.warning("Kokoro package not available, using fallback silence generator")
        pipeline = None
    except Exception as e:
        logger.error(f"Failed to load Kokoro TTS: {e}")
        pipeline = None


# ── Schemas ───────────────────────────────────────────────────────────────────

class SynthesizeRequest(BaseModel):
    text: str
    voice: str = KOKORO_VOICE
    sample_rate: int = KOKORO_SAMPLE_RATE
    speed: float = 1.0


class VoiceInfo(BaseModel):
    id: str
    name: str
    language: str


# ── Core Synthesis ────────────────────────────────────────────────────────────

async def synthesize_streaming(
    text: str,
    voice: str = KOKORO_VOICE,
    speed: float = 1.0,
    sample_rate: int = KOKORO_SAMPLE_RATE,
) -> AsyncGenerator[bytes, None]:
    """Stream PCM int16 audio chunks from Kokoro TTS.

    Kokoro generates audio in sentence-level chunks which we stream back
    as raw PCM bytes for minimal latency.
    """
    if pipeline is None:
        # Fallback: generate 1 second of silence
        logger.warning("TTS pipeline not loaded, generating silence")
        silence = np.zeros(sample_rate, dtype=np.int16)
        yield silence.tobytes()
        return

    try:
        # Kokoro generates audio via a generator that yields (graphemes, phonemes, audio) tuples
        generator = pipeline(
            text,
            voice=voice,
            speed=speed,
        )

        for graphemes, phonemes, audio_chunk in generator:
            if audio_chunk is not None and len(audio_chunk) > 0:
                # audio_chunk is a numpy float32 array in range [-1, 1]
                # Convert to int16 PCM
                audio_int16 = (audio_chunk * 32767).astype(np.int16)

                # Resample if needed (Kokoro outputs at 24000 by default)
                if sample_rate != KOKORO_SAMPLE_RATE and sample_rate > 0:
                    duration = len(audio_int16) / KOKORO_SAMPLE_RATE
                    target_len = int(duration * sample_rate)
                    indices = np.linspace(0, len(audio_int16) - 1, target_len)
                    audio_int16 = np.interp(
                        indices,
                        np.arange(len(audio_int16)),
                        audio_int16.astype(np.float32),
                    ).astype(np.int16)

                yield audio_int16.tobytes()

                # Yield control to event loop between chunks
                await asyncio.sleep(0)

    except Exception as e:
        logger.error(f"TTS synthesis error: {e}")
        # Yield a short silence on error
        silence = np.zeros(sample_rate // 2, dtype=np.int16)
        yield silence.tobytes()


def synthesize_full(
    text: str,
    voice: str = KOKORO_VOICE,
    speed: float = 1.0,
    sample_rate: int = KOKORO_SAMPLE_RATE,
) -> np.ndarray:
    """Generate complete audio for text (non-streaming)."""
    if pipeline is None:
        return np.zeros(sample_rate, dtype=np.int16)

    all_audio = []
    for graphemes, phonemes, audio_chunk in pipeline(text, voice=voice, speed=speed):
        if audio_chunk is not None and len(audio_chunk) > 0:
            audio_int16 = (audio_chunk * 32767).astype(np.int16)
            all_audio.append(audio_int16)

    if all_audio:
        return np.concatenate(all_audio)
    return np.zeros(sample_rate, dtype=np.int16)


# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "model_loaded": pipeline is not None,
        "default_voice": KOKORO_VOICE,
        "sample_rate": KOKORO_SAMPLE_RATE,
        "device": KOKORO_DEVICE,
    }


@app.get("/voices")
async def list_voices():
    """List available TTS voices."""
    return {
        "voices": [
            {"id": v, "name": v.replace("_", " ").title(), "language": "en"}
            for v in AVAILABLE_VOICES
        ],
        "default": KOKORO_VOICE,
    }


@app.post("/synthesize")
async def synthesize(req: SynthesizeRequest):
    """Streaming TTS synthesis — returns raw PCM int16 audio as a stream.

    The client receives audio chunks as they're generated, enabling
    low-latency playback.
    """
    if not req.text.strip():
        return JSONResponse({"error": "Empty text"}, status_code=400)

    async def stream_generator():
        async for chunk in synthesize_streaming(
            text=req.text,
            voice=req.voice,
            speed=req.speed,
            sample_rate=req.sample_rate,
        ):
            yield chunk

    return StreamingResponse(
        stream_generator(),
        media_type="application/octet-stream",
        headers={
            "X-Sample-Rate": str(req.sample_rate),
            "X-Channels": "1",
            "X-Sample-Width": "2",  # 16-bit
        },
    )


@app.post("/synthesize/wav")
async def synthesize_wav(req: SynthesizeRequest):
    """Generate complete WAV file for the given text."""
    if not req.text.strip():
        return JSONResponse({"error": "Empty text"}, status_code=400)

    audio = synthesize_full(
        text=req.text,
        voice=req.voice,
        speed=req.speed,
        sample_rate=req.sample_rate,
    )

    # Create WAV in memory
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(req.sample_rate)
        wf.writeframes(audio.tobytes())

    wav_buffer.seek(0)
    return StreamingResponse(
        wav_buffer,
        media_type="audio/wav",
        headers={"Content-Disposition": "attachment; filename=output.wav"},
    )


@app.websocket("/ws/synthesize")
async def websocket_synthesize(ws: WebSocket):
    """WebSocket endpoint for streaming TTS.

    Protocol:
    1. Client sends JSON: {"text": "Hello world", "voice": "af_heart"}
    2. Server streams binary PCM audio chunks
    3. Server sends JSON: {"status": "done"} when complete
    """
    await ws.accept()
    logger.info("WebSocket TTS connection established")

    try:
        while True:
            data = await ws.receive_json()
            text = data.get("text", "")
            voice = data.get("voice", KOKORO_VOICE)
            speed = data.get("speed", 1.0)

            if not text.strip():
                await ws.send_json({"status": "error", "message": "Empty text"})
                continue

            async for chunk in synthesize_streaming(text, voice=voice, speed=speed):
                await ws.send_bytes(chunk)

            await ws.send_json({"status": "done"})

    except WebSocketDisconnect:
        logger.info("WebSocket TTS connection closed")
    except Exception as e:
        logger.error(f"WebSocket TTS error: {e}")
        await ws.close(code=1011, reason=str(e))


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
