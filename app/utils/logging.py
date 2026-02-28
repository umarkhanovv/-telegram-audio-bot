"""
Structured JSON logging.
Outputs JSON lines in production, human-readable in development.
"""
import logging
import sys
from typing import Any

try:
    import json_log_formatter
    _HAS_JSON_FORMATTER = True
except ImportError:
    _HAS_JSON_FORMATTER = False


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter if json-log-formatter is unavailable."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        import traceback

        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge extra fields
        for key, val in record.__dict__.items():
            if key not in {
                "args", "asctime", "created", "exc_info", "exc_text",
                "filename", "funcName", "id", "levelname", "levelno",
                "lineno", "module", "msecs", "message", "msg", "name",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "thread", "threadName",
            }:
                log_entry[key] = val

        if record.exc_info:
            log_entry["exception"] = traceback.format_exception(*record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    from app.config.settings import settings

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)

    if settings.ENV == "production":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Quiet noisy libraries
    for lib in ("aiogram", "aiohttp", "urllib3"):
        logging.getLogger(lib).setLevel(logging.WARNING)
