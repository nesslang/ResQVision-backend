"""
Structured logging configuration for ResQVision 2.0.
Uses structlog for JSON-formatted (production) or pretty (debug) logs.
Never logs passwords, tokens, or secrets.
"""
import logging
import sys
import structlog
from app.core.config import get_settings

# Fields that must never appear in log output
_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "secret", "token", "access_token",
    "refresh_token", "authorization", "api_key", "private_key",
})


def _drop_sensitive_fields(
    logger: object,
    method: str,
    event_dict: dict,
) -> dict:
    """Structlog processor: scrub sensitive keys from every log record."""
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = "***REDACTED***"
    return event_dict


def setup_logging() -> None:
    """
    Configure structlog + stdlib logging.
    Call once at application startup (main.py lifespan).
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure stdlib root logger
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )
    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Choose renderer based on environment
    if settings.debug:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _drop_sensitive_fields,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    """
    Return a structlog BoundLogger bound to the given name.

    Usage:
        logger = get_logger(__name__)
        logger.info("event_name", key="value")
    """
    return structlog.get_logger(name)


def bind_request_context(
    request_id: str,
    method: str,
    path: str,
    user_id: str | None = None,
) -> None:
    """
    Bind per-request context variables to structlog's context vars.
    Call at the start of each request in middleware.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        method=method,
        path=path,
        **({"user_id": user_id} if user_id else {}),
    )


def clear_request_context() -> None:
    """Clear structlog context vars at the end of a request."""
    structlog.contextvars.clear_contextvars()
