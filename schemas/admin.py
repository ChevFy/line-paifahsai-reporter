from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AdminLogin(BaseModel):
    username: str
    password: str


class AdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    last_login_at: datetime | None
