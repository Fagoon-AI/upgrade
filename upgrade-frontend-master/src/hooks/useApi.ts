import { useState } from "react";
import { API_ENDPOINTS, fetchWithError } from "@/utils/api/api";
import type {
  ChatResponse,
  TranscriptionResponse,
} from "@/types/api";

export const useApi = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendChatMessage = async (
    message: string,
    internet_search: boolean = false, // Changed parameter name
  ): Promise<ChatResponse> => {
    setLoading(true);
    setError(null);

    try {
      return await fetchWithError(API_ENDPOINTS.CHAT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          internet_search, // Changed from webSearch
        }),
      });
    } catch (error) {
      setError(error instanceof Error ? error.message : "An error occurred");
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const transcribeAudio = async (
    audioFile: File,
  ): Promise<TranscriptionResponse> => {
    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("audio", audioFile);

      return await fetchWithError(API_ENDPOINTS.TRANSCRIBE, {
        method: "POST",
        body: formData,
      });
    } catch (error) {
      setError(error instanceof Error ? error.message : "An error occurred");
      throw error;
    } finally {
      setLoading(false);
    }
  };

  // Add other API methods...

  return {
    loading,
    error,
    sendChatMessage,
    transcribeAudio,
    // Other methods...
  };
};
