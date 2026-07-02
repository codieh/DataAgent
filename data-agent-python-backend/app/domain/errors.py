class DomainError(Exception):
    """Base class for expected application errors."""


class ResourceNotFoundError(DomainError):
    def __init__(self, resource: str, resource_id: str):
        self.resource = resource
        self.resource_id = resource_id
        super().__init__(f"{resource} not found: {resource_id}")


class InvalidOperationError(DomainError):
    pass

