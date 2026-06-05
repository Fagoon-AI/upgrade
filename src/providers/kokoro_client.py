from enum import Enum
from kokoro_onnx import Kokoro


class KokoroConfig(Enum):
    VOICE = "bf_emma"
    SPEED = 1.0
    LANGUAGE = "en-us"
    MODEL_PATH = "assets/kokoro_config/kokoro-v1.0.onnx"
    VOICES_PATH = "assets/kokoro_config/voices-v1.0.bin"


def get_client():
    return Kokoro(KokoroConfig.MODEL_PATH.value, KokoroConfig.VOICES_PATH.value)
