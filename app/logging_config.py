# ...existing code...
import logging
import logging.handlers
import os
from pathlib import Path


def _get_log_level_from_env(default: str = "INFO") -> int:
    level_name = os.getenv("LOG_LEVEL", default).upper()
    return getattr(logging, level_name, logging.INFO)


def setup_logging(service_name: str) -> logging.Logger:
    """
    Configure logging for the configuration service.

    Environment variables:
    - LOG_DIR: base directory for logs (default: ./logs/<service_name>)
    - LOG_LEVEL: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
    """
    log_dir = os.getenv("LOG_DIR", f"./logs/{service_name}")

    try:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
    except PermissionError:
        fallback = os.getenv("FALLBACK_LOG_DIR", f"/tmp/{service_name}-logs")
        try:
            Path(fallback).mkdir(parents=True, exist_ok=True)
            log_dir = fallback
        except Exception:
            log_dir = "."

    log_file = Path(log_dir) / f"{service_name}.log"

    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03dZ [%(levelname)s] %(name)s - %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S'
    )

    level = _get_log_level_from_env()

    file_handler = logging.handlers.RotatingFileHandler(
        str(log_file),
        maxBytes=1024 * 1024 * 1024,  # 1GB
        backupCount=30
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    root = logging.getLogger()
    root.setLevel(level)

    if not any(isinstance(h, logging.handlers.RotatingFileHandler) and getattr(h, "baseFilename", "") == str(log_file) for h in root.handlers):
        root.addHandler(file_handler)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(console_handler)

    logger = logging.getLogger(service_name)
    logger.info("Logging initialized. Log file: %s, level: %s", log_file, logging.getLevelName(level))
    return logger
