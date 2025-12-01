# ...existing code...
import logging
import logging.handlers
import os
from pathlib import Path

def setup_logging(service_name):
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

    file_handler = logging.handlers.RotatingFileHandler(
        str(log_file),
        maxBytes=1024*1024*1024,  # 1GB
        backupCount=30
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    if not any(isinstance(h, logging.handlers.RotatingFileHandler) and getattr(h, "baseFilename", "") == str(log_file) for h in root.handlers):
        root.addHandler(file_handler)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(console_handler)

    return logging.getLogger(service_name)
