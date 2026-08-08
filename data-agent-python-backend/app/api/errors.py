"""FastAPI 全局错误处理器。

把领域层抛出的语义化异常映射为统一的 JSON 错误响应，使前端能用一致的
``{code, message}`` 结构处理错误：
- ResourceNotFoundError -> 404（资源不存在）
- InvalidOperationError  -> 409（操作与当前状态冲突）
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.errors import InvalidOperationError, ResourceNotFoundError


def install_error_handlers(app: FastAPI) -> None:
    """注册全局异常处理器到 FastAPI 应用实例。"""

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

