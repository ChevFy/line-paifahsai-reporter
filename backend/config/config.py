from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    LINE_CHANNEL_SECRET: str = Field(min_length=1)
    LINE_CHANNEL_ACCESS_TOKEN: str = Field(min_length=1)
    LINE_LOGIN_CHANNEL_ID: str = Field(min_length=1)
    LIFF_ALLOWED_ORIGINS: list[str] = Field(min_length=1)

    NGROK_AUTH_TOKEN: str = ""
    USE_NGROK: bool = False

    HOST: str = "127.0.0.1"
    PORT: int = 8000

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    POSTGRES_USER: str = Field(min_length=1)
    POSTGRES_PASSWORD: str = Field(min_length=1)
    POSTGRES_HOST: str = Field(min_length=1)
    POSTGRES_PORT: int
    POSTGRES_DB: str = Field(min_length=1)

    S3_ENDPOINT_URL: str = Field(min_length=1)
    S3_REGION: str = Field(min_length=1)
    S3_ACCESS_KEY: str = Field(min_length=1)
    S3_SECRET_KEY: str = Field(min_length=1)
    S3_BUCKET: str = Field(min_length=1)

    PUBLIC_BASE_URL: str = Field(pattern=r"^https://")
    PHOTO_LINK_SECRET: str = Field(min_length=32)

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @model_validator(mode="after")
    def check_ngrok(self) -> Self:
        if self.USE_NGROK and not self.NGROK_AUTH_TOKEN:
            raise ValueError("USE_NGROK=true requires NGROK_AUTH_TOKEN")
        return self


settings = Settings()
