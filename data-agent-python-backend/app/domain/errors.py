"""领域错误类型。

定义业务层可预期、需由上层捕获并转化为友好响应的错误。这些错误与框架无关，
不应被当作未预期异常（500）处理，而是代表「业务规则不允许」等预期失败。
"""

class DomainError(Exception):
    """领域层预期错误的基类。所有业务错误均继承自它。"""


class ResourceNotFoundError(DomainError):
    """请求的资源不存在。携带资源类型与 ID 以便上层给出精确提示。"""

    def __init__(self, resource: str, resource_id: str):
        self.resource = resource
        self.resource_id = resource_id
        super().__init__(f"{resource} not found: {resource_id}")


class InvalidOperationError(DomainError):
    """当前状态下执行了不允许的操作（如对已终态运行再次取消）。"""
    pass

