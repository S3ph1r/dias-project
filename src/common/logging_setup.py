"""
DIAS Structured Logging

Logging JSON strutturato con campi:
  timestamp, stage, book_id, level, message

Output: stderr (per systemd journal) + file rotante opzionale.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Optional


class JsonFormatter(logging.Formatter):
    """Formatter che produce log JSON su una riga."""

    def __init__(self, stage_name: str):
        super().__init__()
        self.stage_name = stage_name

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": self.stage_name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        # Campi extra opzionali (book_id, scene_id, etc.)
        for key in ("book_id", "chapter_id", "scene_id", "block_id", "job_id"):
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value

        # Eccezione se presente
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(
    stage_name: str,
    level: str = "INFO",
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Configura logging strutturato per uno stadio DIAS.

    Args:
        stage_name: Nome dello stadio (es. "stage_a", "stage_b")
        level: Livello di logging (DEBUG, INFO, WARNING, ERROR)
        log_file: Path opzionale per file log rotante

    Returns:
        Logger configurato
    """
    logger = logging.getLogger(f"dias.{stage_name}")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Evita handler duplicati su chiamate multiple
    if logger.handlers:
        logger.handlers.clear()

    formatter = JsonFormatter(stage_name)

    # Handler stderr (sempre attivo)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    # Handler file rotante (opzionale)
    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3,
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Non propagare al root logger
    logger.propagate = False

    return logger


def get_logger(stage_name: str) -> logging.Logger:
    """Ritorna il logger per uno stadio. Se non configurato, lo crea con defaults."""
    logger = logging.getLogger(f"dias.{stage_name}")
    if not logger.handlers:
        return setup_logging(stage_name)
    return logger
