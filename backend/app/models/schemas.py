"""Pydantic schemas for API request/response models."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class SessionStatus(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class TranscriptEntry(BaseModel):
    id: str
    speaker: str  # "agent" | "user"
    text: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_final: bool = True


class CreateSessionRequest(BaseModel):
    customer_name: Optional[str] = "Customer"
    customer_email: Optional[str] = None
    topic: Optional[str] = "general"
    metadata: Optional[dict] = None


class CreateSessionResponse(BaseModel):
    session_id: str
    room_name: str
    livekit_token: str
    livekit_url: str


class SessionInfo(BaseModel):
    session_id: str
    room_name: str
    customer_name: str
    status: SessionStatus
    topic: str
    created_at: datetime
    ended_at: Optional[datetime] = None
    transcript: List[TranscriptEntry] = []
    summary: Optional[str] = None


class EndSessionRequest(BaseModel):
    session_id: str


class EndSessionResponse(BaseModel):
    session_id: str
    status: str
    summary: Optional[str] = None
    duration_seconds: Optional[int] = None


class AgentMessageRequest(BaseModel):
    """For text-based fallback messages from frontend."""
    session_id: str
    text: str


class AgentMessageResponse(BaseModel):
    text: str
    audio_url: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    services: dict
