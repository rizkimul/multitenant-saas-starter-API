class AppError(Exception):
    """Base class for all application domain errors.

    Args:
        message: Human-readable error description.
        status_code: HTTP status code to return to the client.
    """

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NotFoundError(AppError):
    """Raised when a requested resource does not exist.

    Args:
        resource: Name of the resource that was not found.
    """

    def __init__(self, resource: str) -> None:
        super().__init__(f"{resource} not found", status_code=404)


class ConflictError(AppError):
    """Raised when an action conflicts with existing state (e.g. duplicate email).

    Args:
        message: Description of the conflict.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=409)


class UnauthorizedError(AppError):
    """Raised when a request lacks valid authentication credentials.

    Args:
        message: Optional override for the default message.
    """

    def __init__(self, message: str = "Not authenticated") -> None:
        super().__init__(message, status_code=401)


class ForbiddenError(AppError):
    """Raised when an authenticated user lacks permission for an action.

    Args:
        message: Optional override for the default message.
    """

    def __init__(self, message: str = "Not authorized") -> None:
        super().__init__(message, status_code=403)
