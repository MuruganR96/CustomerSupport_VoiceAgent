"""Session management API routes."""

import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException

from ..models.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    EndSessionRequest,
    EndSessionResponse,
    SessionInfo,
    SessionStatus,
)
from ..core.config import get_settings
from ..core.session_store import session_store
from ..services.livekit_service import livekit_service
from ..agent.voice_worker import start_agent_for_session, stop_agent_for_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("/create", response_model=CreateSessionResponse)
async def create_session(req: CreateSessionRequest):
    """Create a new voice support session with a LiveKit room."""
    settings = get_settings()
    session_id = str(uuid.uuid4())
    room_name = f"support-{session_id[:8]}"

    try:
        # Create LiveKit room
        await livekit_service.create_room(room_name)

        # Generate user token
        user_identity = f"user-{req.customer_name or 'customer'}"
        user_token = livekit_service.create_user_token(room_name, user_identity)

        # Store session
        await session_store.create_session(
            session_id=session_id,
            room_name=room_name,
            customer_name=req.customer_name or "Customer",
            topic=req.topic or "general",
        )

        # Start the voice agent worker for this session
        await start_agent_for_session(
            session_id=session_id,
            room_name=room_name,
            customer_name=req.customer_name or "Customer",
        )

        logger.info(f"Session created: {session_id} | room: {room_name}")

        return CreateSessionResponse(
            session_id=session_id,
            room_name=room_name,
            livekit_token=user_token,
            livekit_url=settings.livekit_url,
        )

    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str):
    """Get session details including transcript."""
    session = await session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/end", response_model=EndSessionResponse)
async def end_session(req: EndSessionRequest):
    """End a voice support session."""
    session = await session_store.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Stop the voice agent worker
    await stop_agent_for_session(req.session_id)

    await session_store.update_status(req.session_id, SessionStatus.COMPLETED)

    # Calculate duration
    duration = None
    if session.created_at:
        duration = int((datetime.utcnow() - session.created_at).total_seconds())

    # Clean up LiveKit room
    try:
        await livekit_service.delete_room(session.room_name)
    except Exception as e:
        logger.warning(f"Room cleanup failed: {e}")

    logger.info(f"Session ended: {req.session_id} | duration: {duration}s")

    return EndSessionResponse(
        session_id=req.session_id,
        status="completed",
        summary=session.summary,
        duration_seconds=duration,
    )


@router.get("/", response_model=list)
async def list_sessions():
    """List all sessions."""
    sessions = await session_store.list_sessions()
    return sessions
