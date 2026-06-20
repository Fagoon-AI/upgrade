import axiosInstance from "../axios";

export const createChat = async (data: {
  role: string;
  message: string;
  uuid: string | string[];
  selected_model?: string;
  conversation_id: string | string[];
  user_id: string | null;
  data?: string | null;
  internet_search?: boolean;
  tokenUsage?: number;
  isAssignmentMode?: boolean;
}) => {
  const response = await axiosInstance.post(`/api/v1/chat/create/chat`, data);
  return response.data;
};

export const enhancePrompt = async (query: string) => {
  const response = await axiosInstance.post("/api/v1/enhance", { query });
  return response.data;
};

export const transcribeAudio = async (formData: FormData) => {
  const response = await axiosInstance.post("/api/transcribe", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
};

export const textToSpeech = async (chat: string) => {
  const response = await axiosInstance.post(
    "/api/text-to-speech",
    { chat },
    { responseType: "blob" }
  );
  return response.data;
};

export const getChatHistory = async (historyId: string | string[]) => {
  const response = await axiosInstance.get(`/api/v1/chat/get/chat/${historyId}`);
  return response.data;
};

export const checkTokens = async () => {
  const response = await axiosInstance.get(`/api/v1/chat/checkToken`);
  return response.data;
};

export const initUpgradeChat = async () => {
  const response = await axiosInstance.post("/api/v1/upgrade/chat");
  return response.data;
};

export const getUpgradeChatHistory = async (conversationId: string) => {
  const response = await axiosInstance.get(`/api/v1/upgrade/chat/${conversationId}`);
  return response.data;
};

export const deleteUpgradeConversation = async (conversationId: string) => {
  const response = await axiosInstance.delete(`/api/v1/upgrade/chat/${conversationId}`);
  return response.data;
};

export const getUpgradeChatIds = async () => {
  const response = await axiosInstance.get(`/api/v1/upgrade/chat/conversations`);
  return response.data;
}

export const generateUpgradeChatTitle = async (conversationId: string) => {
  const response = await axiosInstance.post(`/api/v1/upgrade/chat/generate-title?conversation_id=${conversationId}`);
  return response.data;
};

export const streamUpgradeChat = async (payload: {
  conversation_id?: string;
  message: string;
  internet_search?: boolean;
  web_search_enabled?: boolean;
  generate_audio?: boolean;
  selected_model?: string;
  file_data?: string | null;
  file_name?: string | null;
}, signal?: AbortSignal) => {
  let token = "";
  if (typeof window !== "undefined") {
    token = localStorage.getItem("upgrade-token") || "";
    if (!token) {
      const userStorage = localStorage.getItem("user-storage");
      if (userStorage) {
        try {
          const parsed = JSON.parse(userStorage);
          token = parsed.state?.token || "";
        } catch (e) {
          console.error("Error parsing user-storage", e);
        }
      }
    }
  }

  const response = await fetch(`${process.env.NEXT_PUBLIC_BASE_URL || ""}/api/v1/upgrade/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
    credentials: "include",
    signal,
  });

  return response;
};
