import logging
import json
import re
from typing import List, Dict, Any, Optional
from src.schemas.vibe_coder_schemas import CodeGenerationRequest, CodeGenerationResponse
from src.models.sql.vibe_coder_models import UserLLMConfigDB
from src.core.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class UIPrototyperService:
    """Orchestrates LLM calls to generate UI Code (React/Tailwind/HTML)"""
    
    def __init__(self, llm_factory=None):
        self.llm_factory = llm_factory
    
    def _get_llm_instance(self, provider: str, config):
        """Helper to dynamically instantiate the correct LLM class based on provider."""
        if provider == "openai":
            from src.llms.openai_llm import OpenAILLM
            return OpenAILLM(config=config)
        elif provider == "anthropic":
            from src.llms.anthropic_llm import AnthropicLLM
            return AnthropicLLM(config=config)
        elif provider == "gemini":
            from src.llms.gemini_llm import GeminiLLM
            return GeminiLLM(config=config)
        elif provider == "groq":
            from src.llms.groq_llm import GroqLLM
            return GroqLLM(config=config)
        elif provider == "ollama":
            from src.llms.ollama_llm import OllamaLLM
            return OllamaLLM(config=config)
        elif provider == "hugging_face":
            from src.llms.huggingface_llm import HuggingFaceLLM
            return HuggingFaceLLM(config=config)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def _get_fallback_model(self, provider: str, model_id: str) -> str:
        """Fallback to a sensible default if the user provided a generic provider string instead of a specific model ID."""
        if not model_id or model_id.lower() == provider.lower():
            fallbacks = {
                "gemini": "gemini-2.5-flash",
                "openai": "gpt-4o",
                "anthropic": "claude-3-5-sonnet-latest",
                "groq": "llama-3.3-70b-versatile"
            }
            return fallbacks.get(provider.lower(), model_id)
        return model_id

    async def generate_ui_code(
        self,
        request: CodeGenerationRequest,
        user_llm_config: Any,
    ) -> CodeGenerationResponse:
        """
        Call the configured LLM to generate UI code (HTML/React).
        """
        provider = user_llm_config.provider
        model_name = self._get_fallback_model(provider, user_llm_config.model_id)
        api_key = user_llm_config.api_key
            
        system_prompt = self._build_ui_system_prompt()
        
        messages = [{"role": "system", "content": system_prompt}]
        if request.conversation_history:
            messages.extend([{"role": m.role, "content": m.content} for m in request.conversation_history])
        
        messages.append({"role": "user", "content": request.user_prompt})
        
        logger.info(f"Generating UI code using {provider}/{model_name}")
        
        from src.schemas.llm import BaseLLMConfig
        
        if not api_key and provider != "ollama":
             raise ValueError(f"API key for {provider} is missing in your configuration.")

        llm_config = BaseLLMConfig(
            model=model_name,
            provider=provider,
            api_key=api_key,
            temperature=0.7,
            max_tokens=8192
        )
        
        llm = self._get_llm_instance(provider, llm_config)
        
        # The generate method from base LLM wrapper returns the raw text when not streaming,
        # or it returns a parsed dict if tools are used.
        raw_response = await llm.generate(messages=messages, is_stream=False)
        
        if isinstance(raw_response, dict) and "content" in raw_response:
             raw_response = raw_response["content"]
        
        extracted_code = self._extract_code_from_response(str(raw_response))
        
        return CodeGenerationResponse(
            code=extracted_code,
            explanation="I built the requested UI component."
        )

    async def stream_ui_code(
        self,
        request: CodeGenerationRequest,
        user_llm_config: Any,
    ):
        """
        Generator function to stream tokens back to the frontend.
        """
        provider = user_llm_config.provider
        model_name = self._get_fallback_model(provider, user_llm_config.model_id)
        api_key = user_llm_config.api_key
            
        system_prompt = self._build_ui_system_prompt()
        
        messages = [{"role": "system", "content": system_prompt}]
        if request.conversation_history:
            messages.extend([{"role": m.role, "content": m.content} for m in request.conversation_history])
        
        messages.append({"role": "user", "content": request.user_prompt})
        
        from src.schemas.llm import BaseLLMConfig
        
        if not api_key and provider != "ollama":
             raise ValueError(f"API key for {provider} is missing in your configuration.")

        llm_config = BaseLLMConfig(
            model=model_name,
            provider=provider,
            api_key=api_key,
            temperature=0.7,
            max_tokens=8192
        )
        
        llm = self._get_llm_instance(provider, llm_config)
        
        logger.info(f"Streaming UI code using {provider}/{model_name}")
        
        response_stream = await llm.generate(messages=messages, is_stream=True)
        
        # Note: Different providers might stream chunks differently.
        # This handles OpenAI/Gemini/Groq standard streaming chunk structures.
        async for chunk in response_stream:
            # Handle typical OpenAI/Gemini chunk format
            if hasattr(chunk, "choices") and chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None) or getattr(delta, "text", None)
                if content:
                    yield f"data: {json.dumps({'token': content})}\n\n"
            # Handle Anthropic / Text-based streams if different
            elif isinstance(chunk, str):
                yield f"data: {json.dumps({'token': chunk})}\n\n"
            elif hasattr(chunk, "delta") and hasattr(chunk.delta, "text"):
                # Anthropic message delta
                yield f"data: {json.dumps({'token': chunk.delta.text})}\n\n"
                    
        # Send a final [DONE] message to indicate the stream is complete
        yield "data: [DONE]\n\n"
        
    def _build_ui_system_prompt(self) -> str:
        """System prompt designed for pure frontend code generation."""
        return """You are an expert frontend developer and UI designer. 
Your task is to generate a complete, working UI component based on the user's request.

CRITICAL INSTRUCTIONS:
1. You MUST output a SINGLE, self-contained HTML file.
2. Output ONLY the code inside a markdown block (```html ... ```). Do not add any conversational text before or after.
3. The HTML file must use Vanilla JavaScript and Tailwind CSS via CDN. Do NOT use React, Vue, Babel, or any other framework.
4. Write your JavaScript code inside a standard `<script>` tag at the end of the `<body>`.
5. Mount your interactive logic using standard DOM manipulation (e.g., `document.getElementById()`, `addEventListener`).
6. Use Tailwind CSS classes for ALL styling. Do not use custom CSS unless absolutely necessary for complex animations.
7. Make the UI modern, visually appealing, responsive, and interactive.
8. Assume lucide icons are NOT available via import. If you need icons, use FontAwesome classes (e.g., `<i className="fas fa-user"></i>`) and include the FontAwesome CDN link in the `<head>`.

Here is the exact boilerplate structure you MUST follow:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generated UI</title>
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- FontAwesome for Icons -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-gray-50 min-h-screen text-gray-900">
    <div id="app">
        <!-- Build the requested UI here -->
        <div class="flex items-center justify-center min-h-screen bg-green-100">
             <h1 class="text-6xl font-extrabold text-green-700 drop-shadow-lg animate-pulse" id="greeting">
                 Hello World!
             </h1>
        </div>
    </div>

    <script>
        // Your Vanilla JavaScript logic goes here!
        document.addEventListener('DOMContentLoaded', () => {
            const greeting = document.getElementById('greeting');
            if (greeting) {
                greeting.addEventListener('click', () => {
                    alert('Clicked!');
                });
            }
        });
    </script>
</body>
</html>
```
"""

    def _extract_code_from_response(self, response_text: str) -> str:
        """Extract code from LLM response (markdown code block)"""
        # Try to find a properly closed markdown block
        match = re.search(r'```(?:html|tsx|jsx|typescript|ts|javascript|js)?\n(.*?)\n```', response_text, re.DOTALL)
        if match:
            return match.group(1).strip()
            
        # Try to find an unclosed markdown block (LLM output was truncated)
        match = re.search(r'```(?:html|tsx|jsx|typescript|ts|javascript|js)?\n(.*)', response_text, re.DOTALL)
        if match:
            return match.group(1).strip()
            
        # If the LLM completely ignored the markdown block and just started writing HTML
        clean_text = response_text.strip()
        if clean_text.startswith("<!DOCTYPE html>") or clean_text.startswith("<html"):
            # Strip trailing markdown if it randomly appended it without an opening tag
            clean_text = re.sub(r'\n```$', '', clean_text)
            return clean_text
            
        return clean_text
