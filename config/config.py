from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    LINE_CHANNEL_SECRET: str = Field(min_length=1)
    LINE_CHANNEL_ACCESS_TOKEN: str = Field(min_length=1)

    NGROK_AUTH_TOKEN: str = ""
    USE_NGROK: bool = False

    HOST: str = "127.0.0.1"
    PORT: int = 8000

    @model_validator(mode="after")
    def check_ngrok(self) -> Self:
        if self.USE_NGROK and not self.NGROK_AUTH_TOKEN:
            raise ValueError("USE_NGROK=true requires NGROK_AUTH_TOKEN")
        return self


settings = Settings()
