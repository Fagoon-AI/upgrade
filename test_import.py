import sys
import os
from loguru import logger

# Add the current directory to sys.path
sys.path.append(os.getcwd())

logger.info("Starting test import...")
try:
    from src.launch_server import app
    logger.info("Import successful!")
except Exception as e:
    logger.error(f"Import failed: {e}")
    import traceback
    traceback.print_exc()
