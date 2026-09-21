import json
import logging
from datetime import datetime, timezone


SENSITIVE_KEYS = frozenset({"token", "message", "raw_result", "authorization"})


class JsonFormatter(logging.Formatter):
    """Single-line JSON per log record; extra_fields are promoted to top-level keys."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_fields"):
            for key, value in record.extra_fields.items():
                if key.lower() not in SENSITIVE_KEYS:
                    log_entry[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception_type"] = record.exc_info[0].__name__
        return json.dumps(log_entry, default=str)


class SensitiveFieldFilter(logging.Filter):
    """Redacts log messages that embed sensitive values (tokens, messages, raw payloads)."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for key in SENSITIVE_KEYS:
            if key in msg.lower():
                record.msg = "[REDACTED - contained sensitive field]"
                record.args = None
        return True


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler.addFilter(SensitiveFieldFilter())
        root.addHandler(handler)
