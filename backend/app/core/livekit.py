"""LiveKit integration: mint join tokens and verify/parse webhooks.

When LiveKit is configured, it owns the media (audio/video) and emits
`participant_joined` / `participant_left` webhooks. We translate those into the
same `PresenceEvent` log the attendance engine already understands — so the
attendance pipeline is identical whether media flows over the built-in mesh or
over LiveKit. The participant `identity` we set on the token is the user id, so
webhooks map cleanly back to a user.
"""
from livekit import api

from app.config import settings


def create_join_token(room_name: str, user_id: int, display_name: str) -> str:
    """Mint a short-lived token that lets a user join one LiveKit room."""
    grants = api.VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True)
    return (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(str(user_id))
        .with_name(display_name)
        .with_grants(grants)
        .to_jwt()
    )


def webhook_receiver() -> api.WebhookReceiver:
    return api.WebhookReceiver(api.TokenVerifier(settings.livekit_api_key, settings.livekit_api_secret))
