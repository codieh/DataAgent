"""应用级异常。

预期的业务失败由上层转换为结构化结果；未预期的编程错误继续向上抛出，不能静默吞掉。
"""


class AppError(Exception):
    """可安全展示给用户的业务异常。"""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class ConfigurationError(AppError):
    def __init__(self, message: str):
        super().__init__("configuration_error", message)


class TenantAccessError(AppError):
    def __init__(self, message: str = "当前资源不属于请求租户"):
        super().__init__("tenant_access_denied", message)


class ResourceNotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__("resource_not_found", f"{resource} not found: {resource_id}")
