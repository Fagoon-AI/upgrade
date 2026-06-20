import axiosInstance, { axiosStream } from "../axios";

export const generateCode = async (
  user_prompt: string,
  conversation_history: { role: "user" | "assistant"; content: string }[],
  llm_config_id: string
) => {
  const baseURL = axiosStream.defaults.baseURL || '';

  const response = await fetch(`${baseURL}/api/v1/vibe/generate/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      user_prompt,
      available_tools: [],
      conversation_history,
      user_preferences: {
        additionalProp1: {}
      },
      llm_config_id
    })
  });
  return response;
};

// New non-streaming API helper for normal output
export const generateVibeCode = async (
  user_prompt: string,
  conversation_history: { role: "user" | "assistant"; content: string }[],
  llm_config_id: string
) => {
  const response = await axiosInstance.post("/api/v1/vibe/generate", {
    user_prompt,
    available_tools: [],
    conversation_history,
    user_preferences: {
      additionalProp1: {}
    },
    llm_config_id,
  });
  return response.data;
};
