"""Whisper Streaming STT Service.

In-house Speech-to-Text microservice wrapping OpenAI Whisper.
Exposes a simple HTTP API:
  POST /transcribe — accepts raw PCM audio bytes, returns transcribed text
  POST /transcribe/file — accepts WAV file upload
  GET  /health — health check
  WS   /ws/transcribe — WebSocket streaming transcription
"""

import io
import os
import wave
import logging
import tempfile
import asyncio
from typing import Optional

import numpy as np
import torch
import whisper
from fastapi import FastAPI, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
DEFAULT_SAMPLE_RATE = 16000  # Whisper expects 16kHz
DEFAULT_CHANNELS = 1

# ── Model Loading ─────────────────────────────────────────────────────────────

app = FastAPI(title="Whisper STT Service", version="1.0.0")

model: Optional[whisper.Whisper] = None


@app.on_event("startup")
async def load_model():
    global model
    logger.info(f"Loading Whisper model: {WHISPER_MODEL} on {WHISPER_DEVICE}")
    model = whisper.load_model(WHISPER_MODEL, device=WHISPER_DEVICE)
    logger.info(f"Whisper model loaded successfully")


# ── Utilities ─────────────────────────────────────────────────────────────────

def pcm_to_float32(pcm_bytes: bytes, sample_rate: int = 24000) -> np.ndarray:
    """Convert raw PCM int16 bytes to float32 numpy array normalized to [-1, 1].
    Also resample to 16kHz if needed (Whisper requirement).
    """
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    # Resample to 16kHz if input is different
    if sample_rate != DEFAULT_SAMPLE_RATE:
        # Simple resampling using linear interpolation
        duration = len(audio) / sample_rate
        target_length = int(duration * DEFAULT_SAMPLE_RATE)
        indices = np.linspace(0, len(audio) - 1, target_length)
        audio = np.interp(indices, np.arange(len(audio)), audio)

    return audio


def transcribe_audio(audio: np.ndarray, language: str = "en") -> dict:
    """Run Whisper transcription on float32 audio array."""
    if model is None:
        raise RuntimeError("Model not loaded")

    # Pad or trim to 30 seconds (Whisper's expected input length)
    audio = whisper.pad_or_trim(audio)

    # Create log-mel spectrogram
    mel = whisper.log_mel_spectrogram(audio).to(model.device)

    # Detect language if not specified
    if language == "auto":
        _, probs = model.detect_language(mel)
        language = max(probs, key=probs.get)

    # Decode
    options = whisper.DecodingOptions(
        language=language,
        fp16=(WHISPER_DEVICE == "cuda"),
        without_timestamps=True,
    )
    result = whisper.decode(model, mel, options)

    return {
        "text": result.text.strip(),
        "language": language,
        "no_speech_prob": float(result.no_speech_prob),
    }


# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "model": WHISPER_MODEL,
        "device": WHISPER_DEVICE,
        "model_loaded": model is not None,
    }


@app.post("/transcribe")
async def transcribe_pcm(request: Request):
    """Transcribe raw PCM audio bytes.

    Headers:
        X-Sample-Rate: Input sample rate (default: 24000)
        X-Channels: Number of channels (default: 1)
        X-Language: Language code (default: en, use 'auto' for detection)
    """
    body = await request.body()
    if not body or len(body) < 100:
        return JSONResponse({"text": "", "error": "Audio too short"})

    sample_rate = int(request.headers.get("X-Sample-Rate", "24000"))
    language = request.headers.get("X-Language", "en")

    try:
        audio = pcm_to_float32(body, sample_rate=sample_rate)

        # Skip if audio is mostly silence
        if np.max(np.abs(audio)) < 0.01:
            return JSONResponse({"text": "", "is_silence": True})

        result = transcribe_audio(audio, language=language)

        # Skip high no-speech probability results
        if result["no_speech_prob"] > 0.8:
            return JSONResponse({"text": "", "no_speech_prob": result["no_speech_prob"]})

        return JSONResponse(result)

    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return JSONResponse({"text": "", "error": str(e)}, status_code=500)


@app.post("/transcribe/file")
async def transcribe_file(file: UploadFile = File(...), language: str = "en"):
    """Transcribe an uploaded WAV/audio file."""
    try:
        contents = await file.read()

        # Save to temp file for Whisper
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        # Use Whisper's built-in file loading
        audio = whisper.load_audio(tmp_path)
        os.unlink(tmp_path)

        result = transcribe_audio(audio, language=language)
        return JSONResponse(result)

    except Exception as e:
        logger.error(f"File transcription error: {e}")
        return JSONResponse({"text": "", "error": str(e)}, status_code=500)


@app.websocket("/ws/transcribe")
async def websocket_transcribe(ws: WebSocket):
    """WebSocket endpoint for streaming transcription.

    Protocol:
    1. Client sends binary PCM audio frames
    2. Server accumulates frames and transcribes when silence detected
    3. Server sends JSON: {"text": "...", "is_final": true/false}
    """
    await ws.accept()
    logger.info("WebSocket STT connection established")

    buffer = bytearray()
    silence_count = 0
    SILENCE_THRESHOLD = 0.01
    SILENCE_FRAMES_TO_COMMIT = 25  # ~500ms at 20ms frames

    try:
        while True:
            data = await ws.receive_bytes()

            audio_chunk = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            rms = np.sqrt(np.mean(audio_chunk**2))

            if rms > SILENCE_THRESHOLD:
                buffer.extend(data)
                silence_count = 0
            else:
                if len(buffer) > 0:
                    silence_count += 1
                    buffer.extend(data)

                    if silence_count >= SILENCE_FRAMES_TO_COMMIT:
                        # Transcribe accumulated audio
                        audio = pcm_to_float32(bytes(buffer))
                        buffer.clear()
                        silence_count = 0

                        if len(audio) > 1600:  # At least 100ms of audio
                            result = transcribe_audio(audio)
                            if result["text"] and result["no_speech_prob"] < 0.8:
                                await ws.send_json({
                                    "text": result["text"],
                                    "is_final": True,
                                    "language": result["language"],
                                })

    except WebSocketDisconnect:
        logger.info("WebSocket STT connection closed")
    except Exception as e:
        logger.error(f"WebSocket STT error: {e}")
        await ws.close(code=1011, reason=str(e))


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
