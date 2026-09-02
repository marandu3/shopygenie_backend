from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Base application error. Carries a stable machine-readable `code`."""

    def __init__(self, code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", code: str = "NOT_FOUND"):
        super().__init__(code=code, message=message, status_code=status.HTTP_404_NOT_FOUND)


class ConflictError(AppError):
    def __init__(self, message: str, code: str = "CONFLICT"):
        super().__init__(code=code, message=message, status_code=status.HTTP_409_CONFLICT)


class ValidationAppError(AppError):
    def __init__(self, message: str, code: str = "VALIDATION_ERROR"):
        super().__init__(code=code, message=message, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Authentication required", code: str = "UNAUTHORIZED"):
        super().__init__(code=code, message=message, status_code=status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(AppError):
    def __init__(self, message: str = "You do not have permission to perform this action", code: str = "FORBIDDEN"):
        super().__init__(code=code, message=message, status_code=status.HTTP_403_FORBIDDEN)


class InsufficientStockError(AppError):
    def __init__(self, product_name: str, available: int, requested: int):
        super().__init__(
            code="INSUFFICIENT_STOCK",
            message=f"Insufficient stock for '{product_name}'. Available: {available}, requested: {requested}",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


def _envelope(code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}}


def register_exception_handlers(app) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=_envelope(exc.code, exc.message))

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content=_envelope("HTTP_ERROR", str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else None
        message = f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}" if first else "Invalid request"
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=_envelope("VALIDATION_ERROR", message))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Never leak stack traces / internals to the client.
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=_envelope("INTERNAL_ERROR", "An unexpected error occurred."))
