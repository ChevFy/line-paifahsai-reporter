from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    LINE_CHANNEL_SECRET: str = ""
    LINE_CHANNEL_ACCESS_TOKEN: str = ""

    NGROK_AUTH_TOKEN: str = ""
    USE_NGROK: bool = False

    HOST: str = "127.0.0.1"
    PORT: int = 8000


settings = Settings()
