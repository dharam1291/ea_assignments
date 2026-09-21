class GatewayError(Exception):
    """Base for all gateway-layer errors that map to an HTTP status + error envelope."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class AuthenticationError(GatewayError):
    def __init__(self, message: str = "Invalid or missing credentials.") -> None:
        super().__init__(code="UNAUTHORIZED", message=message)


class AuthorizationError(GatewayError):
    def __init__(self, message: str = "Insufficient permissions.") -> None:
        super().__init__(code="FORBIDDEN", message=message)


class CapabilityNotFoundError(GatewayError):
    def __init__(self, message: str = "The requested capability does not exist.") -> None:
        super().__init__(code="CAPABILITY_NOT_FOUND", message=message)


class InputValidationError(GatewayError):
    def __init__(self, message: str = "Invalid request input.") -> None:
        super().__init__(code="VALIDATION_ERROR", message=message)


class UpstreamUnavailableError(GatewayError):
    def __init__(self, message: str = "The upstream service is temporarily unavailable.") -> None:
        super().__init__(code="UPSTREAM_UNAVAILABLE", message=message)


class UpstreamPermanentError(GatewayError):
    def __init__(self, message: str = "The upstream service returned a permanent error.") -> None:
        super().__init__(code="UPSTREAM_PERMANENT", message=message)


class InvalidToolResultError(GatewayError):
    def __init__(self, message: str = "The tool returned an invalid result.") -> None:
        super().__init__(code="INVALID_TOOL_RESULT", message=message)


class UpstreamTimeoutError(GatewayError):
    def __init__(self, message: str = "The tool did not respond in time.") -> None:
        super().__init__(code="UPSTREAM_TIMEOUT", message=message)


class TransientError(Exception):
    """Raised by adapters for retryable failures (network blips, 503, etc.)."""


class PermanentError(Exception):
    """Raised by adapters for non-retryable failures (4xx, schema mismatch, etc.)."""
