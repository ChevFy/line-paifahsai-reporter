from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.db import close_db
from line.line_client import close_line_bot_api
from line.line_webhook import router as line_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_line_bot_api()
    await close_db()


app = FastAPI(lifespan=lifespan)

app.include_router(line_router)


@app.get("/healthz")
def health_check():
    return {"status": "OK"}

