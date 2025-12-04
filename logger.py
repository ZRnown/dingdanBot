import logging
import os
from logging.handlers import TimedRotatingFileHandler
from config import Config


LOG_DIR = getattr(Config, "LOG_DIR", "logs")
LOG_RETENTION_DAYS = getattr(Config, "LOG_RETENTION_DAYS", 7)

os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("kefuBot")
logger.setLevel(logging.INFO)

if not logger.handlers:
    formatter = logging.Formatter("%(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = TimedRotatingFileHandler(
        filename=os.path.join(LOG_DIR, "bot.log"),
        when="midnight",
        backupCount=LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def log(message: str) -> None:
    """统一日志函数：既写文件又输出到终端，内容保持一致"""
    logger.info(message)


