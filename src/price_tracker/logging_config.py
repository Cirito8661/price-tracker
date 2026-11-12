"""Logging setup for console and rotating file output."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from .config import Settings

_HANDLER_MARKER = "_price_tracker_handler"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _remove_our_handlers(root: logging.Logger) -> None:
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            root.removeHandler(handler)
            handler.close()


def configure_logging(settings: Settings) -> None:
    """Configure root logging without disturbing external handlers."""

    root = logging.getLogger()
    _remove_our_handlers(root)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT)

    console_handler = logging.StreamHandler(stream=sys.stderr)
    console_handler.setFormatter(formatter)
    setattr(console_handler, _HANDLER_MARKER, True)
    root.addHandler(console_handler)

    try:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            settings.log_dir / "app.log",
            maxBytes=5_000_000,
            backupCount=5,
            encoding="utf-8",
        )
    except OSError:
        logging.getLogger(__name__).warning(
            "Could not create the file log handler; continuing with console logging.",
            exc_info=True,
        )
    else:
        file_handler.setFormatter(formatter)
        setattr(file_handler, _HANDLER_MARKER, True)
        root.addHandler(file_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


def reset_logging() -> None:
    """Remove and close handlers installed by :func:`configure_logging`."""

    _remove_our_handlers(logging.getLogger())
