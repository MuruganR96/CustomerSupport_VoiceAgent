"""In-memory session store (can be replaced with Redis for production)."""

import asyncio
import json
from datetime import datetime
from typing import Optional, Dict, List
from ..models.schemas import SessionInfo, SessionStatus, TranscriptEntry


class SessionStore:
    """Thread-safe session storage using asyncio locks."""

    def __init__(self):
        self._sessions: Dict[str, SessionInfo] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        session_id: str,
        room_name: str,
        customer_name: str = "Customer",
        topic: str = "general",
    ) -> SessionInfo:
        async with self._lock:
            session = SessionInfo(
                session_id=session_id,
                room_name=room_name,
                customer_name=customer_name,
                status=SessionStatus.CREATED,
                topic=topic,
                created_at=datetime.utcnow(),
            )
            self._sessions[session_id] = session
            return session

    async def get_session(self, session_id: str) -> Optional[SessionInfo]:
        async with self._lock:
            return self._sessions.get(session_id)

    async def update_status(self, session_id: str, status: SessionStatus):
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].status = status
                if status == SessionStatus.COMPLETED:
                    self._sessions[session_id].ended_at = datetime.utcnow()

    async def add_transcript(self, session_id: str, entry: TranscriptEntry):
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].transcript.append(entry)

    async def set_summary(self, session_id: str, summary: str):
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].summary = summary

    async def list_sessions(self) -> List[SessionInfo]:
        async with self._lock:
            return list(self._sessions.values())

    async def delete_session(self, session_id: str):
        async with self._lock:
            self._sessions.pop(session_id, None)


# Global singleton
session_store = SessionStore()
