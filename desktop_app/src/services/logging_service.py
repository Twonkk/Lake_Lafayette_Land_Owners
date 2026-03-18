from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import threading
import traceback

from src.runtime import APP_NAME, APP_VERSION, AppPaths


LOGGER_NAME = "lakelot"


def configure_logging(paths: AppPaths) -> Path:
    log_path = paths.logs_dir / "app.log"
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logger.info("Application startup requested: %s v%s", APP_NAME, APP_VERSION)
    logger.info("Data dir: %s", paths.data_dir)
    logger.info("Database path: %s", paths.db_path)
    logger.info("Legacy dir: %s", paths.legacy_dir)
    return log_path


def get_logger(name: str | None = None) -> logging.Logger:
    base = logging.getLogger(LOGGER_NAME)
    return base if not name else base.getChild(name)


def install_global_exception_logging() -> None:
    logger = get_logger("crash")

    def _sys_hook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.error(
            "Unhandled exception\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
        )
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    def _thread_hook(args: threading.ExceptHookArgs) -> None:
        logger.error(
            "Unhandled thread exception\n%s",
            "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
        )

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook
