from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    anthropic_api_key: str = ""
    # Free-tier alternatives. Every Gemini/Groq key that is set joins one rotating pool
    # (services/llm.py): each call goes to the next key, and a rate-limited key is skipped
    # until it cools down. Keys can be given one per variable or comma-separated.
    gemini_api_key: str = ""
    gemini_api_keys: str = ""
    groq_api_key: str = ""
    groq_api_key_2: str = ""
    groq_api_key_3: str = ""
    groq_api_key_4: str = ""
    groq_api_keys: str = ""
    llm_model: str = ""
    admin_key: str = "change-me"
    # The /demo endpoints (scenario switch, fast-forward, seed) need no key so the phone's
    # demo panel can call them. Set DEMO_MODE=false anywhere that is not a demo.
    demo_mode: bool = True
    database_url: str = "sqlite:///./seasafe.db"
    monitor_interval: int = 60
    twilio_sid: str = ""
    twilio_token: str = ""
    twilio_from: str = ""
    telegram_bot_token: str = ""
    # Voice assistant limits per fisher. The key pool has its own per-key cool-down on top.
    assistant_per_minute: int = 6
    assistant_per_day: int = 120
    community_per_minute: int = 8


def _split(*values: str) -> list[str]:
    out: list[str] = []
    for v in values:
        for part in (v or "").split(","):
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return out


settings = Settings()


def groq_keys() -> list[str]:
    s = settings
    return _split(s.groq_api_key, s.groq_api_key_2, s.groq_api_key_3, s.groq_api_key_4, s.groq_api_keys)


def gemini_keys() -> list[str]:
    return _split(settings.gemini_api_key, settings.gemini_api_keys)
