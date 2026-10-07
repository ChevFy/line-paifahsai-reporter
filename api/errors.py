import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

VALIDATION_MESSAGE = "ข้อมูลไม่ถูกต้อง กรุณาตรวจสอบแล้วลองอีกครั้ง"


async def handle_validation_error(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    logger.warning(
        "invalid request: method=%s path=%s errors=%s",
        request.method,
        request.url.path,
        error.errors(),
    )
    detail = {
        "message": VALIDATION_MESSAGE,
        "errors": jsonable_encoder(error.errors()),
    }
    return JSONResponse(status_code=422, content={"detail": detail})


async def handle_http_error(
    request: Request, error: StarletteHTTPException
) -> JSONResponse:
    detail = error.detail
    if not isinstance(detail, dict):
        detail = {"message": str(detail)}
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": detail},
        headers=error.headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
