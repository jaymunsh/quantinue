"""Single structured logging setup for development and production."""

import logging

import structlog


def configure_logging(*, debug: bool) -> None:
    """Configure a stable structured event stream."""
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, format="%(message)s")
    for logger_name in ("httpx", "httpcore", "httpx2", "httpcore2", "hpack"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
    )
