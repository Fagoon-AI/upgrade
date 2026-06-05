from dotenv import load_dotenv
from loguru import logger
import os
import sys

load_dotenv()

ENVIRONMENT_MODE = os.getenv("LOGS_ENVIRONMENT_MODE", "development")

def setup_logging():
    os.makedirs("logs", exist_ok=True)
    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    common_config = {
        "rotation": "1 month",
        "retention": "3 months",
        "compression": "zip",
        "enqueue": True,
    }

    # Level-based log files
    logger.add(
        "logs/debug.log",
        level="DEBUG",
        filter=lambda r: r["level"].name == "DEBUG",
        format=log_format,
        **common_config,
    )
    logger.add(
        "logs/success.log",
        level="SUCCESS",
        filter=lambda r: r["level"].name == "SUCCESS",
        format=log_format,
        **common_config,
    )
    logger.add(
        "logs/warning.log",
        level="WARNING",
        filter=lambda r: r["level"].name == "WARNING",
        format=log_format,
        **common_config,
    )
    logger.add(
        "logs/error.log",
        level="ERROR",
        filter=lambda r: r["level"].name == "ERROR",
        format=log_format,
        **common_config,
    )

    logger.add("logs/app.log", level="DEBUG", format=log_format, **common_config)

    if ENVIRONMENT_MODE == "production":
        logger.add("logs/app.json", level="INFO", serialize=True, **common_config)

    logger.add(sys.stderr, format=log_format)
