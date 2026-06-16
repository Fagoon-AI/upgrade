from loguru import logger
import asyncio

from src.services.agents.llm_tasks import generate_general_chat_response

class MermaidService:
    def __init__(self):
        logger.info("MermaidService initialized for markdown generation.")

    async def generate_mermaid_code(self, prompt: str, model_name: str, user_id: str = None) -> str:
        """Uses an LLM to generate Mermaid markdown from a user prompt."""
        logger.info("Generating Mermaid markdown for prompt using model: {}.", model_name)

        system_prompt = (
            "You are a world-class expert in Mermaid.js syntax. Your sole task is to generate clean, "
            "efficient, and syntactically perfect Mermaid markdown based on the user's request. "
            "ONLY output the raw markdown code inside a ```mermaid code block. "
            "Do not include any other text, explanations, or introductory phrases."
        )

        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]

        try:
            full_response = "".join([chunk async for chunk in generate_general_chat_response(
                messages=messages, 
                model_name=model_name,
                user_id=user_id,
                feature="chat"
            )])

            if "```mermaid" in full_response:
                code = full_response.split("```mermaid")[1].split("```")[0].strip()
                if not code:
                    raise ValueError("LLM returned an empty Mermaid code block.")
                logger.success("Successfully extracted Mermaid markdown from LLM response.")
                return code
            else:
                logger.error("LLM did not return a valid Mermaid code block. Response: {response}", response=full_response)
                raise ValueError("Failed to generate a valid Mermaid diagram from the prompt.")
        except Exception as e:
            logger.error("An error occurred during Mermaid code generation: {}", e, exc_info=True)
            raise RuntimeError("Could not generate diagram code. The model may have had trouble with the request.") from e