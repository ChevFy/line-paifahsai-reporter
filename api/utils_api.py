import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.districts import router as districts_router
from api.errors import register_error_handlers
from api.incidents import router as incidents_router
from api.reports import router as reports_router
from api.volunteers import router as volunteers_router
from config.config import settings
from core.db import SessionLocal, close_db
from core.log_config import setup_logging
from jobs.worker import log_worker_exit, run_worker, wake_worker
from line.line_client import close_line_bot_api
from line.line_id_token import close_id_token_client
from line.line_webhook import router as line_router

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_worker = asyncio.Event()
    worker = asyncio.create_task(run_worker(SessionLocal, stop_worker))
    worker.add_done_callback(log_worker_exit)
    yield
    stop_worker.set()
    wake_worker()
    await worker
    await close_id_token_client()
    await close_line_bot_api()
    await close_db()


app = FastAPI(lifespan=lifespan)
register_error_handlers(app)

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
app.include_router(incidents_router)
app.include_router(volunteers_router)


@app.get("/healthz")
def health_check():
    return {"status": "OK"}
