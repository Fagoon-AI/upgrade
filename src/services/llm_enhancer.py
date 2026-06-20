import uuid
from typing import Optional
import httpx

from loguru import logger
from src.core.settings import system_setting


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


async def enhance_prompt_text_async(original_prompt: str, user_id: Optional[uuid.UUID] = None) -> str:
    """
    Enhances the given prompt using Groq or Gemini LLM.
    """
    api_key = None
    if user_id:
        from src.services.api_key_resolver import resolve_api_key
        try:
            resolved_key = await resolve_api_key(
                user_id=user_id,
                provider="groq",
                feature="chat"
            )
            if resolved_key:
                api_key = resolved_key
        except Exception as e:
            logger.error(f"Error resolving key for prompt enhancer: {e}")

    if not api_key:
        api_key = system_setting.GROQ_API_KEY

    if not api_key or api_key == "YOUR_GROQ_API_KEY":
        logger.warning("GROQ_API_KEY not configured or resolved. Returning original prompt.")
        return f"{original_prompt}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a creative assistant that enhances user prompts for an AI video "
                    "generator. Make the prompts more vivid, descriptive, and cinematic. "
                    "Add details about art style, camera angles, lighting, and mood if appropriate. "
                    "Keep the enhanced prompt concise yet impactful, focusing on visual elements. "
                    "CRITICAL: Output ONLY the raw enhanced prompt. Do NOT include any conversational filler, "
                    "preambles, introductions, or lists of choices (e.g., do NOT start with 'Sure, here is...', "
                    "'Here are a few cinematic options...', etc.). Your response must contain ONLY the single "
                    "vivid paragraph of the prompt itself, ready to be sent to the video generator."
                ),
            },
            {
                "role": "user",
                "content": original_prompt,
            },
        ],
        "temperature": 0.7,
        "max_tokens": 200,
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(api_url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()
            enhanced_text = data["choices"][0]["message"]["content"].strip()
            logger.info("Prompt enhanced using {}: '{}' -> '{}'", provider_name, original_prompt, enhanced_text)
            return enhanced_text
    except httpx.TimeoutException:
        logger.error("{} API request timed out for prompt: '{}'", provider_name, original_prompt)
        raise Exception("LLM API request timed out.")
    except httpx.RequestError as e:
        logger.error("Error calling {} API for prompt '{}': {}", provider_name, original_prompt, e)
        raise Exception(f"LLM API request failed: {e}")
    except (KeyError, IndexError, TypeError) as e:
        logger.error(
            "Error parsing {} API response: {} - Response: {}", provider_name, e, response.text if 'response' in locals() else 'No response object'
        )
        raise Exception(f"LLM API response parsing failed: {e}")
    except Exception as e:
        logger.error("An unexpected error occurred during prompt enhancement: {}", e)
        raise Exception(f"Unexpected error in LLM enhancement: {e}")
