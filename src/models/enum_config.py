from enum import Enum

class ResponseStatus(Enum):
    SUCCESS = "success"
    FAIL = "fail"

class UserType(Enum):
    GENERAL = "general"
    PRO = "pro"

class AvailableLLMModel(Enum):
    OPENAI = "openai"
    GROQ = "groq"
    HUGGINGFACE = "hugging_face"

class AvailableDiffusionModel(Enum):
    HUGGINGFACE = "hugging_face"
    OPENAI = "openai"

class InferenceProvider(Enum):
    HUGGINGFACE_INFERENCE = "hf-inference"
    FAL_AI = "fal-ai"
    REPLICATE = "replicate"

class AvailableTTSModelProvider(Enum):
    HUGGINGFACE = "hugging_face"
    OPENAI = "openai"
    ELEVEN_LABS = "eleven_labs"
    FAGOON = "fagoon"

class OpenAITTSModel(Enum):
    TTS_1 = "tts-1"

class CoreSystemConfig(Enum):
    MAX_TOKEN = 1000

class AvailableTextToVideoProvider(Enum):
    HUGGINGFACE = "hugging_face"
    GOOGLE = "google"

class TextToVideoAvailableModel(Enum):
    GENMO_MOCHI = "genmo/mochi-1-preview"
