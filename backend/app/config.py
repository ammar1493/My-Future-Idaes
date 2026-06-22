"""Application configuration loaded from environment variables."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    app_name: str = "LiveTrain"
    environment: str = "development"
    secret_key: str = "change-me-in-production-this-is-not-secure"
    access_token_expire_minutes: int = 60 * 12

    # Database
    database_url: str = "postgresql+psycopg://livetrain:livetrain@localhost:5432/livetrain"

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # LiveKit (production media server). When key/secret/url are all set, the
    # platform uses LiveKit for video and derives attendance from LiveKit
    # webhooks. When unset, it falls back to the built-in WebRTC mesh.
    livekit_url: str = ""          # wss://your-project.livekit.cloud
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    @property
    def livekit_enabled(self) -> bool:
        return bool(self.livekit_url and self.livekit_api_key and self.livekit_api_secret)

    # Attendance policy defaults (overridable per course)
    # Minimum share of a session a student must be present to be counted "present".
    attendance_present_threshold: float = 0.75
    # Below this share counts as "partial"; under partial floor counts as "absent".
    attendance_partial_threshold: float = 0.25
    # How often (seconds) a connected client must heartbeat to be considered live.
    presence_heartbeat_seconds: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
