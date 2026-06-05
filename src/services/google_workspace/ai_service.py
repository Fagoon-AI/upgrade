from typing import Optional
from loguru import logger
from groq import Groq
from src.core.settings import system_setting


class AIService:
    """
    Service for integrating with AI models (e.g., for summarization, reply generation) using Groq.
    """

    def __init__(self):
        if not system_setting.GROQ_API_KEY:
            logger.warning(
                "GROQ_API_KEY is not set. AI Service will use placeholder logic."
            )
            self.client = None
        else:
            try:
                self.client = Groq(api_key=system_setting.GROQ_API_KEY)
                logger.info(
                    f"Groq AI Service initialized with model: {system_setting.GROQ_MODEL_NAME}."
                )
            except Exception as e:
                logger.error(
                    f"Failed to initialize Groq client: {e}. AI Service will use placeholder logic.",
                    exc_info=True,
                )
                self.client = None

    async def _call_groq_api(
        self, system_prompt: str, user_prompt: str
    ) -> Optional[str]:
        """Helper to call the Groq API."""
        if not self.client:
            logger.warning("Groq client not initialized. Using placeholder.")
            return None

        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
                model=system_setting.GROQ_MODEL_NAME,
                temperature=0.7,
                max_tokens=1024,
            )
            return chat_completion.choices[0].message.content
        except Exception as e:
            logger.error(f"Error calling Groq API: {e}", exc_info=True)
            return None

    async def summarize_text(self, text: str) -> str:
        """
        Summarizes the given text using an AI model.
        """
        if not text:
            return "No content to summarize."

        system_prompt = "You are a helpful assistant specialized in summarizing text. Provide a concise and accurate summary of the user's input."
        user_prompt = f"Please summarize the following text:\n\n{text}"

        summary = await self._call_groq_api(system_prompt, user_prompt)
        if summary:
            return summary
        else:
            logger.warning(
                "Groq summarization failed, falling back to basic placeholder."
            )
            return f'AI Summary: This is a placeholder summary for a long text. Original text starts with: "{text[:150]}..."'

    async def generate_reply(
        self,
        original_message_content: str,
        context: Optional[str] = None,
        persona: Optional[str] = None,
    ) -> str:
        """
        Generates a reply to an email using an AI model.
        """
        if not original_message_content:
            return "No content to generate a reply from."

        system_prompt = "You are a helpful assistant that generates professional and concise email replies. Maintain a polite and helpful tone."
        user_prompt = f"Original message: {original_message_content}\n"
        if context:
            user_prompt += f"Additional context: {context}\n"
        if persona:
            user_prompt += f"Adopt the following persona: {persona}\n"
        user_prompt += "Please generate a suitable reply to this email."

        reply = await self._call_groq_api(system_prompt, user_prompt)
        if reply:
            return reply
        else:
            logger.warning(
                "Groq reply generation failed, falling back to basic placeholder."
            )
            return f"AI Generated Reply (Placeholder): Thank you for your email. I've noted the content and will get back to you shortly. (Prompt used: {user_prompt[:100]}...)"

    async def generate_text_from_prompt(self, prompt: str) -> str:
        """
        Generates text based on a given prompt using an AI model.
        """
        if not prompt:
            return "Please provide a prompt for text generation."

        system_prompt = "You are a creative and helpful AI assistant that generates high-quality text based on user prompts."
        user_prompt = f"Generate text based on the following instructions:\n\n{prompt}"

        generated_text = await self._call_groq_api(system_prompt, user_prompt)
        if generated_text:
            return generated_text
        else:
            logger.warning(
                "Groq text generation failed, falling back to basic placeholder."
            )
            return f'AI Generated Text (Placeholder): Could not generate text for your prompt: "{prompt[:100]}..."'
