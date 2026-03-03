"""LiveKit room and token management service."""

import logging
from livekit.api import LiveKitAPI, AccessToken, VideoGrants

from ..core.config import get_settings

logger = logging.getLogger(__name__)


class LiveKitService:
    """Manages LiveKit rooms, tokens, and dispatches."""

    def __init__(self):
        self.settings = get_settings()

    def create_user_token(self, room_name: str, identity: str) -> str:
        """Generate a LiveKit access token for a user (customer)."""
        token = AccessToken(
            api_key=self.settings.livekit_api_key,
            api_secret=self.settings.livekit_api_secret,
        )
        token.identity = identity
        token.name = identity
        token.add_grant(
            VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        # Token valid for 6 hours
        token.ttl = 6 * 3600
        return token.to_jwt()

    def create_agent_token(self, room_name: str, identity: str = "agent") -> str:
        """Generate a LiveKit access token for the voice agent."""
        token = AccessToken(
            api_key=self.settings.livekit_api_key,
            api_secret=self.settings.livekit_api_secret,
        )
        token.identity = identity
        token.name = "Support Agent"
        token.add_grant(
            VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                room_admin=True,
            )
        )
        token.ttl = 6 * 3600
        return token.to_jwt()

    async def create_room(self, room_name: str) -> dict:
        """Create a LiveKit room via the API."""
        api = LiveKitAPI(
            url=self.settings.livekit_url.replace("ws://", "http://").replace(
                "wss://", "https://"
            ),
            api_key=self.settings.livekit_api_key,
            api_secret=self.settings.livekit_api_secret,
        )
        try:
            from livekit.api import CreateRoomRequest

            room = await api.room.create_room(
                CreateRoomRequest(
                    name=room_name,
                    empty_timeout=300,  # 5 min empty timeout
                    max_participants=3,
                )
            )
            logger.info(f"Created LiveKit room: {room_name}")
            return {"name": room.name, "sid": room.sid}
        except Exception as e:
            logger.error(f"Failed to create room {room_name}: {e}")
            raise
        finally:
            await api.aclose()

    async def delete_room(self, room_name: str):
        """Delete a LiveKit room."""
        api = LiveKitAPI(
            url=self.settings.livekit_url.replace("ws://", "http://").replace(
                "wss://", "https://"
            ),
            api_key=self.settings.livekit_api_key,
            api_secret=self.settings.livekit_api_secret,
        )
        try:
            from livekit.api import DeleteRoomRequest

            await api.room.delete_room(DeleteRoomRequest(room=room_name))
            logger.info(f"Deleted LiveKit room: {room_name}")
        except Exception as e:
            logger.warning(f"Failed to delete room {room_name}: {e}")
        finally:
            await api.aclose()


# Global singleton
livekit_service = LiveKitService()
