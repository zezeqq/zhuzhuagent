from __future__ import annotations

import logging

from utils.path_utils import log_dir, log_file
from utils.security import mask_secret


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = record.msg.replace("api_key", "api_key_masked")
        return True


def setup_logger() -> logging.Logger:
    log_dir()
    logger = logging.getLogger("dna_agent")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(log_file(), encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SecretFilter())
    logger.addHandler(file_handler)
    return logger
