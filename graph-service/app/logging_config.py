"""JSON logs with token and webhook redaction."""

from __future__ import annotations

import logging
import re

_SECRET = re.compile(
    r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*|client_secret=[^&\s]+|sig=[^&\s]+|access_token=[^&\s]+",
    re.IGNORECASE,
)


def redact(value: str) -> str:
    return _SECRET.sub(lambda match: match.group(0).split("=")[0].split(" ")[0] + " [redacted]", value)


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(redact(arg) if isinstance(arg, str) else arg for arg in record.args)
        return True


def configure_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_opspilot_configured", False):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('{"level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}'))
    handler.addFilter(_RedactFilter())
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root._opspilot_configured = True  # type: ignore[attr-defined]
