import axiosInstance from "../axios";

export const generateCode = async (payload: { prompt: string, llm_config: { model_id: string, provider: string, model_name: string } }) => {
  const response = await axiosInstance.post("/api/code", payload);
  return response.data;
};
