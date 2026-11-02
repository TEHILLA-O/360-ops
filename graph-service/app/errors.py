"""Public errors. Responses never include stack traces or tokens."""


class OpsError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        *,
        category: str = "non_retryable",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.category = category


def public_error(exc: OpsError) -> dict[str, str]:
    return {"error_code": exc.code, "message": exc.message}
