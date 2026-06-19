import axiosInstance from "../axios";
import { AgentFormData } from "../../schemas/agent";

export const createAgent = async (data: AgentFormData & { user_id: string; agent_id?: string | null }) => {
  const response = await axiosInstance.post("/api/v1/agent", data);
  return response.data;
};

export const uploadAgentFile = async (formData: FormData) => {
  const response = await axiosInstance.post("/api/v1/file", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
};

export const getAgentDetails = async (agentId: string) => {
  const response = await axiosInstance.get(`/api/v1/agent/${agentId}`);
  return response.data;
};

export const getMyAgents = async () => {
  const response = await axiosInstance.get(`/api/v1/agent`);
  return response.data;
};

export const listAgents = async (userId: string) => {
  const response = await axiosInstance.get(`/api/v1/agent?user_id=${userId}`);
  return response.data;
};

export const getAgentWebhookConfig = async (agentId: string) => {
  const response = await axiosInstance.get(`/api/v1/agent/${agentId}/webhook-config`);
  return response.data;
};

export const setAgentChannelConfig = async (agentId: string, data: any) => {
  const response = await axiosInstance.post(`/api/v1/agent/${agentId}/channel-config`, data);
  return response.data;
};

export const startWhatsAppSession = async (agentId: string) => {
  const response = await axiosInstance.post(`/api/v1/whatsapp-session/start`, { agent_id: agentId });
  return response.data;
};

export const stopWhatsAppSession = async (agentId: string) => {
  const response = await axiosInstance.delete(`/api/v1/whatsapp-session/${agentId}`);
  return response.data;
};

export const updateAgent = async (agentId: string, data: Partial<AgentFormData>) => {
  const response = await axiosInstance.patch(`/api/v1/agent/${agentId}`, data);
  return response.data;
};

export const deleteAgent = async (agentId: string) => {
  const response = await axiosInstance.delete(`/api/v1/agent/${agentId}`);
  return response.data;
};
