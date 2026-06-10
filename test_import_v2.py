import sys
import os
import time
from loguru import logger

sys.path.append(os.getcwd())

imports = [
    "from src.api.custom_middleware import LoggingMiddleware, AuthMiddleware",
    "from src.api.logging_config import setup_logging",
    "from src.core.settings import system_setting",
    "from src.core.database.postgres import PostgresManager",
    "from src.api.setup_api import setup_and_combine_all_routers",
    "from src.launch_server import app"
]

for imp in imports:
    logger.info(f"Trying: {imp}")
    start = time.time()
    exec(imp)
    logger.info(f"Success in {time.time() - start:.2f}s")
