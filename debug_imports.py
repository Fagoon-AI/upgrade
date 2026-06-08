import time

def timed_import(module_name):
    start = time.time()
    print(f"Importing {module_name}...", end="", flush=True)
    try:
        __import__(module_name)
        print(f" done in {time.time() - start:.2f}s")
    except Exception as e:
        print(f" failed: {e}")

modules = [
    "os",
    "asyncio",
    "httpx",
    "loguru",
    "fastapi",
    "src.core.settings",
    "src.api.logging_config",
    "src.core.database.postgres",
    "src.api.setup_api",
    "src.launch_server"
]

for m in modules:
    timed_import(m)
