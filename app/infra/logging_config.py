"""
Structured JSON logging for HostingGuard.

Every log record is emitted as a single JSON line with:
  - timestamp  (ISO-8601 UTC)
  - level      (INFO, WARNING, ERROR, …)
  - logger     (module name)
  - request_id (from CorrelationMiddleware ContextVar — "-" if outside a request)
  - message
  - extra fields set by the caller (exc_info, stack trace, etc.)

Usage — call setup_logging() once at application startup (main.py):

    from app.infra.logging_config import setup_logging
    setup_logging()
"""
import json
import logging
import traceback
from datetime import datetime, timezone


class _StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        from app.api.correlation import request_id_var

        payload: dict = {
            "ts":         datetime.now(timezone.utc).isoformat(),
            "level":      record.levelname,
            "logger":     record.name,
            "request_id": request_id_var.get(),
            "msg":        record.getMessage(),
        }

        if record.exc_info:
            payload["exc"] = "".join(traceback.format_exception(*record.exc_info)).strip()

        # Merge any extra= fields the caller passed
        for key, val in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = val

        return json.dumps(payload, default=str, ensure_ascii=False)


# Keys that are part of the standard LogRecord — skip them in "extra" merging
_STANDARD_ATTRS = frozenset({
    "name", "msg", "args", "created", "filename", "funcName", "levelname",
    "levelno", "lineno", "module", "msecs", "message", "pathname", "process",
    "processName", "relativeCreated", "stack_info", "thread", "threadName",
    "exc_info", "exc_text",
})


def setup_logging(level: int = logging.INFO) -> None:
    """
    Replaces the root logger's handlers with a single structured JSON handler.
    Call once at application startup, before any other logging happens.
    """
    formatter = _StructuredFormatter()

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Silence noisy third-party loggers that don't add value in prod
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
