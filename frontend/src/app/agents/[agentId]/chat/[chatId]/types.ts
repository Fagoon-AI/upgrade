export type IAgentMessage = {
    role: "user" | "assistant"
    message: {
        logs?: string,
        toolSelection?: string,
        image?: string,
        data: string,
    }
}

export enum IAgentResponseType {
    TOOL_SELECTION = "tool_selection",
    LLM_RESPONSE = "llm_response",
    STATUS = "status",
    IMAGE="image",
    ERROR = "error",
}