from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.districts import router as districts_router
from api.reports import router as reports_router
from config.config import settings
from core.db import close_db
from core.log_config import setup_logging
from line.line_client import close_line_bot_api
from line.line_id_token import close_id_token_client
from line.line_webhook import router as line_router

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_id_token_client()
    await close_line_bot_api()
    await close_db()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.LIFF_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)

app.include_router(line_router)
app.include_router(reports_router)
app.include_router(districts_router)


@app.get("/healthz")
def health_check():
    return {"status": "OK"}
