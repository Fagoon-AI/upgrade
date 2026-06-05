import httpx

from loguru import logger
from src.core.settings import system_setting


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


async def enhance_prompt_text_async(original_prompt: str) -> str:
    """
    Enhances the given prompt using Groq LLM.
    """
    if not system_setting.GROQ_API_KEY or system_setting.GROQ_API_KEY == "YOUR_GROQ_API_KEY":
        logger.warning("GROQ_API_KEY not configured. Returning original prompt.")
        return f"{original_prompt}"

    headers = {
        "Authorization": f"Bearer {system_setting.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama3-8b-8192",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a creative assistant that enhances user prompts for an AI video "
                    "generator. Make the prompts more vivid, descriptive, and cinematic. "
                    "Add details about art style, camera angles, lighting, and mood if appropriate. "
                    "Keep the enhanced prompt concise yet impactful, focusing on visual elements."
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
            response = await client.post(GROQ_API_URL, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()
            enhanced_text = data["choices"][0]["message"]["content"].strip()
            logger.info(f"Prompt enhanced: '{original_prompt}' -> '{enhanced_text}'")
            return enhanced_text
    except httpx.TimeoutException:
        logger.error(f"Groq API request timed out for prompt: '{original_prompt}'")
        raise Exception("LLM API request timed out.")
    except httpx.RequestError as e:
        logger.error(f"Error calling Groq API for prompt '{original_prompt}': {e}")
        raise Exception(f"LLM API request failed: {e}")
    except (KeyError, IndexError, TypeError) as e:
        logger.error(
            f"Error parsing Groq API response: {e} - Response: {response.text if 'response' in locals() else 'No response object'}"
        )
        raise Exception(f"LLM API response parsing failed: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during prompt enhancement: {e}")
        raise Exception(f"Unexpected error in LLM enhancement: {e}")
