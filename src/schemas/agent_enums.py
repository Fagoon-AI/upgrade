from enum import Enum


class SystemPrompt(str, Enum):
    TOOL_SELECTION = "tool_selection"
    IMAGE_ENHANCER = "image_enhancer"
    CHAT_TITLE_GENERATION = "chat_title_generation"


class ToolType(str, Enum):
    GENERAL = "general"
    WEB_SEARCH = "web_search"
    IMAGE_GENERATION = "image_generation"
    MERMAID_DIAGRAM = "mermaid_diagram"
    DEEP_RESEARCH = "deep_research"
    SUMMARIZATION = "summarization"
    NOTE_TAKING = "note_taking"
    AUDIO_GENERATION = "audio_generation"


TOOL_USAGE_GUIDE = {
    ToolType.GENERAL: "Can use its own knowledge base and general knowledge.",
    ToolType.WEB_SEARCH: "Use this tool if you are confident that user requests real-time, current, or factual data that may require a web search.",
    ToolType.IMAGE_GENERATION: "Use this if you are confident that user is requesting you to create a new picture based on their description. This DOES NOT support generating charts or graphs. It is for creative images.",
    ToolType.MERMAID_DIAGRAM: "Use this tool if you are confident that user refers to diagrams such as flowcharts, sequences, or process maps.",
    ToolType.DEEP_RESEARCH: "Use this tool if you are confident that user requests in-depth exploration, comparison, or step-by-step analysis.",
    ToolType.SUMMARIZATION: "Use this tool if you are confident that user asks for a shorter version, recap, or summary of long content.",
    ToolType.NOTE_TAKING: "Use this tool if you are confident that user wants to keep track of tasks, ideas, or take meeting-style notes.",
}


SYSTEM_PROMPTS = {
    SystemPrompt.TOOL_SELECTION: """You are a tool selector for an AI agent.

    Below is a list of available tools and their purposes:
    {tool_info}

    Based on the following recent conversation history, determine which tools should be used.
    Only consider the last two user-assistant interactions (up to 4 messages total).

    Return ONLY a valid JSON array of the tools that should be used.
    Use ONLY the identifiers exactly as listed above.

    Conversation history:
    {conversation_text}

    Respond with a JSON array only. Example: ["summarization", "web_search"]
    Do NOT include explanations or formatting.
    """,
    SystemPrompt.IMAGE_ENHANCER: """ You are an advanced visual description generator. Your task is to create a richly detailed, immersive image description in natural prose to guide high-fidelity image rendering.

    Use and integrate the following sources of context to enrich the image:
    User Prompt: 
    {user_prompt}

    Conversation History: 
    {conversation_history}

    Your output must:
    - Retain important elements and instructions from the conversation
    - Be deeply visual, painting a scene through vivid language
    - Include positional details (e.g., subject posture, orientation, placement within the scene)
    - Specify lighting, time of day, weather conditions, and atmosphere
    - Reference artistic or photographic styles when implied or appropriate (e.g., soft watercolor, cinematic realism, oil painting, anime; or camera specs like 85mm lens, f/1.4, shallow depth of field, low-angle shot)

    Return **only** the enhanced visual description in well-written, natural prose. Do not include explanations, metadata, or formatting tags.
    """,
    SystemPrompt.CHAT_TITLE_GENERATION: """
    You are a smart, helpful title generator. Given a conversation, extract its subject and generate a crisp, informative title using 4–8 words (maximum 10). The title should accurately reflect the main topic

    Conversation History:
    {chat_history}

    Assistant:  
    """.strip(),
}
