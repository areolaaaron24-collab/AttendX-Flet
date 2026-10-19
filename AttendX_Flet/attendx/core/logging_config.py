from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(level: str = "INFO", log_dir: Path | None = None) -> None:
    directory = log_dir or Path(__file__).resolve().parents[2] / "logs"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        file_handler: logging.Handler = RotatingFileHandler(
            directory / "attendx.log", maxBytes=1_000_000, backupCount=4, encoding="utf-8"
        )
    except OSError:
        file_handler = logging.NullHandler()
    console_handler = logging.StreamHandler()
    logging.basicConfig(
        level=getattr(logging, (level or "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[file_handler, console_handler],
        force=True,
    )
