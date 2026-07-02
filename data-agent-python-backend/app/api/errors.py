from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.errors import InvalidOperationError, ResourceNotFoundError


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ResourceNotFoundError)
    async def resource_not_found(_request: Request, error: ResourceNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"code": "resource_not_found", "message": str(error)},
        )

    @app.exception_handler(InvalidOperationError)
    async def invalid_operation(_request: Request, error: InvalidOperationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"code": "invalid_operation", "message": str(error)},
        )

