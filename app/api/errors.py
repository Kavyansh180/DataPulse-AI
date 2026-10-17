import logging
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("datapulse.errors")


class APIError(Exception):
    """Custom application exception with structured error code and message."""

    def __init__(
        self,
        status_code: int,
        message: str,
        code: str = "BAD_REQUEST",
        details: Optional[Any] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        self.details = details


def register_error_handlers(app: FastAPI) -> None:
    """Register custom exception handlers for consistent API error responses."""

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            status.HTTP_404_NOT_FOUND: "NOT_FOUND",
            status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
            status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
            status.HTTP_403_FORBIDDEN: "FORBIDDEN",
            status.HTTP_409_CONFLICT: "CONFLICT",
            status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMIT_EXCEEDED",
            status.HTTP_502_BAD_GATEWAY: "BAD_GATEWAY",
            status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
            status.HTTP_504_GATEWAY_TIMEOUT: "GATEWAY_TIMEOUT",
        }
        error_code = code_map.get(exc.status_code, "HTTP_ERROR")

        # In case exc.detail is already a dict or string
        detail = exc.detail
        message = detail if isinstance(detail, str) else "An HTTP error occurred"
        extra_details = detail if isinstance(detail, (dict, list)) else None

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": error_code,
                    "message": message,
                    "details": extra_details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Simplify validation error list for client readability
        formatted_errors = []
        raw_details = []
        for err in exc.errors():
            loc = " -> ".join([str(x) for x in err.get("loc", []) if x != "body"])
            formatted_errors.append({
                "field": loc or "body",
                "message": err.get("msg", "Invalid input"),
                "type": err.get("type", "value_error"),
                "loc": err.get("loc", []),
                "msg": err.get("msg", "Invalid input"),
            })
            raw_details.append({
                "loc": err.get("loc", []),
                "msg": err.get("msg", "Invalid input"),
                "type": err.get("type", "value_error"),
            })

        return JSONResponse(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Input validation failed for the submitted payload.",
                    "details": formatted_errors,
                },
                "detail": raw_details,
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        # Log internally without leaking credentials or database topology
        logger.error(f"Database error on {request.method} {request.url.path}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "DATABASE_ERROR",
                    "message": "An unexpected database operation error occurred.",
                    "details": None,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled server error on {request.method} {request.url.path}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An internal server error occurred.",
                    "details": None,
                }
            },
        )
