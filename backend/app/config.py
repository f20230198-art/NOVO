from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    anthropic_api_key: str = ""
    admin_key: str = "change-me"
    database_url: str = "sqlite:///./seasafe.db"
    monitor_interval: int = 60
    twilio_sid: str = ""
    twilio_token: str = ""
    twilio_from: str = ""
    telegram_bot_token: str = ""


settings = Settings()
