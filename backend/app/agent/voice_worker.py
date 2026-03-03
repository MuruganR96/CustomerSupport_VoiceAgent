"""LiveKit voice agent worker — bridges LiveKit audio with LangGraph agent.

This worker:
1. Connects to a LiveKit room
2. Receives user audio → sends to Whisper STT service (streaming)
3. Gets transcribed text → sends to LangGraph agent
4. Gets agent response → sends to Kokoro TTS service (streaming)
5. Publishes TTS audio back to the LiveKit room
"""

import asyncio
import json
import logging
import struct
import numpy as np
from datetime import datetime

import httpx
from livekit import rtc

from ..core.config import get_settings
from ..core.session_store import session_store
from ..models.schemas import TranscriptEntry, SessionStatus
from .graph import CustomerSupportAgent

logger = logging.getLogger(__name__)

# Global agent instance (shared across sessions)
_agent: CustomerSupportAgent | None = None


def get_agent() -> CustomerSupportAgent:
    global _agent
    if _agent is None:
        _agent = CustomerSupportAgent()
    return _agent


class VoiceAgentWorker:
    """Manages a single voice session in a LiveKit room."""

    SAMPLE_RATE = 24000
    CHANNELS = 1
    FRAME_DURATION_MS = 20  # 20ms frames
    SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_DURATION_MS // 1000  # 480

    def __init__(self, session_id: str, room_name: str, customer_name: str = "there"):
        self.session_id = session_id
        self.room_name = room_name
        self.customer_name = customer_name
        self.settings = get_settings()
        self.agent = get_agent()
        self.room: rtc.Room | None = None
        self.audio_source: rtc.AudioSource | None = None
        self._running = False
        self._stt_buffer = bytearray()
        self._stt_silence_frames = 0
        self._is_agent_speaking = False

        # VAD parameters
        self._vad_threshold = 0.01  # RMS threshold for speech detection
        self._silence_frames_to_commit = 30  # ~600ms of silence to commit

    async def start(self):
        """Connect to LiveKit room and start the agent loop."""
        self._running = True

        # Create LiveKit room connection
        self.room = rtc.Room()

        # Set up event handlers
        self.room.on("track_subscribed", self._on_track_subscribed)
        self.room.on("participant_disconnected", self._on_participant_disconnected)
        self.room.on("data_received", self._on_data_received)

        # Generate agent token and connect
        from ..services.livekit_service import livekit_service
        agent_token = livekit_service.create_agent_token(self.room_name, "support-agent")

        livekit_url = self.settings.livekit_url
        await self.room.connect(livekit_url, agent_token)
        logger.info(f"Agent connected to room: {self.room_name}")

        # Create audio source for publishing TTS audio
        self.audio_source = rtc.AudioSource(self.SAMPLE_RATE, self.CHANNELS)
        track = rtc.LocalAudioTrack.create_audio_track("agent-audio", self.audio_source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await self.room.local_participant.publish_track(track, options)

        # Update session status
        await session_store.update_status(self.session_id, SessionStatus.ACTIVE)

        # Send greeting
        greeting = await self.agent.get_greeting(self.session_id, self.customer_name)
        await self._speak(greeting)

        # Store greeting in transcript
        await session_store.add_transcript(
            self.session_id,
            TranscriptEntry(
                id=f"t-{datetime.utcnow().timestamp()}",
                speaker="agent",
                text=greeting,
            ),
        )

        # Send greeting as data message for chat UI
        await self._send_data_message("agent", greeting)

    async def stop(self):
        """Disconnect from the room."""
        self._running = False
        if self.room:
            await self.room.disconnect()
        logger.info(f"Agent disconnected from room: {self.room_name}")

    # ── Audio Event Handlers ──────────────────────────────────────────────────

    def _on_track_subscribed(
        self,
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        """Handle incoming audio track from user."""
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            audio_stream = rtc.AudioStream(track, sample_rate=self.SAMPLE_RATE)
            asyncio.create_task(self._process_audio_stream(audio_stream, participant))
            logger.info(f"Subscribed to audio from: {participant.identity}")

    def _on_participant_disconnected(self, participant: rtc.RemoteParticipant):
        """Handle user disconnection."""
        logger.info(f"Participant disconnected: {participant.identity}")
        asyncio.create_task(self.stop())

    def _on_data_received(self, data: rtc.DataPacket):
        """Handle data channel messages (e.g., text input from UI)."""
        try:
            payload = json.loads(data.data.decode("utf-8"))
            if payload.get("type") == "text_message":
                text = payload.get("text", "")
                if text:
                    asyncio.create_task(self._handle_user_text(text))
        except Exception as e:
            logger.warning(f"Failed to parse data message: {e}")

    # ── Audio Processing Pipeline ─────────────────────────────────────────────

    async def _process_audio_stream(
        self, stream: rtc.AudioStream, participant: rtc.RemoteParticipant
    ):
        """Process incoming audio: VAD → STT → Agent → TTS → publish."""
        logger.info("Audio processing pipeline started")

        async for event in stream:
            if not self._running:
                break

            frame_data = event.frame.data.tobytes()

            # Simple energy-based VAD
            samples = np.frombuffer(frame_data, dtype=np.int16).astype(np.float32)
            rms = np.sqrt(np.mean(samples**2)) / 32768.0

            if rms > self._vad_threshold:
                # Speech detected
                self._stt_buffer.extend(frame_data)
                self._stt_silence_frames = 0
            else:
                # Silence
                if len(self._stt_buffer) > 0:
                    self._stt_silence_frames += 1
                    self._stt_buffer.extend(frame_data)

                    # Enough silence → commit utterance
                    if self._stt_silence_frames >= self._silence_frames_to_commit:
                        if not self._is_agent_speaking:
                            audio_bytes = bytes(self._stt_buffer)
                            self._stt_buffer.clear()
                            self._stt_silence_frames = 0
                            asyncio.create_task(
                                self._process_utterance(audio_bytes)
                            )
                        else:
                            # Agent is speaking, discard to avoid echo
                            self._stt_buffer.clear()
                            self._stt_silence_frames = 0

        logger.info("Audio processing pipeline stopped")

    async def _process_utterance(self, audio_bytes: bytes):
        """Send audio to STT, get text, process through agent, speak response."""
        # 1. STT: Send audio to Whisper service
        transcribed_text = await self._transcribe(audio_bytes)
        if not transcribed_text or len(transcribed_text.strip()) < 2:
            return  # Skip empty/noise transcriptions

        logger.info(f"User said: {transcribed_text}")

        # Store user transcript
        await session_store.add_transcript(
            self.session_id,
            TranscriptEntry(
                id=f"t-{datetime.utcnow().timestamp()}",
                speaker="user",
                text=transcribed_text,
            ),
        )
        await self._send_data_message("user", transcribed_text)

        # 2. Agent: Process through LangGraph
        await self._handle_user_text(transcribed_text)

    async def _handle_user_text(self, text: str):
        """Process user text through the LangGraph agent and speak the response."""
        # Send "thinking" indicator
        await self._send_data_message("agent_thinking", "")

        agent_response = await self.agent.process_message(self.session_id, text)

        # Check for call end signal
        call_ended = False
        if agent_response.startswith("CALL_END:"):
            agent_response = agent_response[len("CALL_END:"):]
            call_ended = True

        logger.info(f"Agent response: {agent_response}")

        # Store agent transcript
        await session_store.add_transcript(
            self.session_id,
            TranscriptEntry(
                id=f"t-{datetime.utcnow().timestamp()}",
                speaker="agent",
                text=agent_response,
            ),
        )
        await self._send_data_message("agent", agent_response)

        # 3. TTS: Speak the response
        await self._speak(agent_response)

        if call_ended:
            await asyncio.sleep(2)  # Let TTS finish
            await self.stop()

    # ── STT Integration ───────────────────────────────────────────────────────

    async def _transcribe(self, audio_bytes: bytes) -> str:
        """Send audio to the Whisper STT service and get text back."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.settings.stt_service_url}/transcribe",
                    content=audio_bytes,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "X-Sample-Rate": str(self.SAMPLE_RATE),
                        "X-Channels": str(self.CHANNELS),
                    },
                )
                if response.status_code == 200:
                    result = response.json()
                    return result.get("text", "")
                else:
                    logger.error(f"STT error: {response.status_code} {response.text}")
                    return ""
        except Exception as e:
            logger.error(f"STT service error: {e}")
            return ""

    # ── TTS Integration ───────────────────────────────────────────────────────

    async def _speak(self, text: str):
        """Send text to Kokoro TTS service and publish audio frames to LiveKit."""
        self._is_agent_speaking = True
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Stream TTS audio
                async with client.stream(
                    "POST",
                    f"{self.settings.tts_service_url}/synthesize",
                    json={
                        "text": text,
                        "voice": "af_heart",
                        "sample_rate": self.SAMPLE_RATE,
                    },
                ) as response:
                    if response.status_code != 200:
                        logger.error(f"TTS error: {response.status_code}")
                        return

                    buffer = bytearray()
                    frame_bytes = self.SAMPLES_PER_FRAME * 2  # 16-bit = 2 bytes per sample

                    async for chunk in response.aiter_bytes():
                        buffer.extend(chunk)

                        # Publish complete frames
                        while len(buffer) >= frame_bytes:
                            frame_data = bytes(buffer[:frame_bytes])
                            del buffer[:frame_bytes]

                            # Create LiveKit audio frame
                            samples = np.frombuffer(frame_data, dtype=np.int16)
                            audio_frame = rtc.AudioFrame(
                                data=samples.tobytes(),
                                sample_rate=self.SAMPLE_RATE,
                                num_channels=self.CHANNELS,
                                samples_per_channel=self.SAMPLES_PER_FRAME,
                            )
                            await self.audio_source.capture_frame(audio_frame)

                    # Flush remaining buffer (pad with silence if needed)
                    if len(buffer) > 0:
                        buffer.extend(b'\x00' * (frame_bytes - len(buffer)))
                        samples = np.frombuffer(bytes(buffer), dtype=np.int16)
                        audio_frame = rtc.AudioFrame(
                            data=samples.tobytes(),
                            sample_rate=self.SAMPLE_RATE,
                            num_channels=self.CHANNELS,
                            samples_per_channel=self.SAMPLES_PER_FRAME,
                        )
                        await self.audio_source.capture_frame(audio_frame)

        except Exception as e:
            logger.error(f"TTS streaming error: {e}")
        finally:
            self._is_agent_speaking = False

    # ── Data Channel ──────────────────────────────────────────────────────────

    async def _send_data_message(self, speaker: str, text: str):
        """Send a transcript/status message over LiveKit data channel."""
        if not self.room or not self.room.local_participant:
            return

        payload = json.dumps({
            "type": "transcript" if speaker in ("agent", "user") else speaker,
            "speaker": speaker,
            "text": text,
            "timestamp": datetime.utcnow().isoformat(),
        }).encode("utf-8")

        try:
            await self.room.local_participant.publish_data(
                payload, reliable=True
            )
        except Exception as e:
            logger.warning(f"Failed to send data message: {e}")


# ── Worker Manager ────────────────────────────────────────────────────────────

_active_workers: dict[str, VoiceAgentWorker] = {}


async def start_agent_for_session(
    session_id: str, room_name: str, customer_name: str = "there"
) -> VoiceAgentWorker:
    """Start a voice agent worker for a session."""
    worker = VoiceAgentWorker(session_id, room_name, customer_name)
    _active_workers[session_id] = worker
    asyncio.create_task(worker.start())
    return worker


async def stop_agent_for_session(session_id: str):
    """Stop the voice agent worker for a session."""
    worker = _active_workers.pop(session_id, None)
    if worker:
        await worker.stop()
