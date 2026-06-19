export const API_BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || process.env.NEXT_BASE_PUBLIC_URL || "";
// export const API_BASE_URL = "http://localhost:4000";


export const API_ENDPOINTS = {
  // CHAT: `https://saugatregmi.ekrasunya.com/upgrade/api/stream/chat`,
  // AGENT:'http://localhost:2321/api/v1',
  AGENT: `${API_BASE_URL}/api/v1`,
  CHAT: `${API_BASE_URL}/upgrade/api/chat`,
  TRANSCRIBE: `${API_BASE_URL}/gpt/api/v1/transcribe/`,
  UPLOAD: `${API_BASE_URL}/upgrade/api/upload`,
  EVALUATE: `${API_BASE_URL}/chateval/api/chat/evaluate`,
  IMAGEN: `${API_BASE_URL}/upgrade/api/imagen`,
} as const;

export const fetchWithError = async (
  url: string,
  options: RequestInit = {},
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
): Promise<any> => {
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        ...options.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`API request failed: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error("API Error:", error);
    throw error;
  }
};
