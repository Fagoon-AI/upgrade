import { ModelConfig } from "@/lib/schemas/model";
import axiosInstance from "../axios";

export const listModels = async () => {
    const response = await axiosInstance.get("/api/v1/llm-models/providers");
    return response.data;
};

export const getModels = async () => {
    const response = await axiosInstance.get("/api/v1/llm-models");
    return response.data;
};

export const createModel = async (data: ModelConfig) => {
    const response = await axiosInstance.post("/api/v1/llm-models", data);
    return response.data;
};

export const getModelById = async (id: string) => {
    const response = await axiosInstance.get(`/api/v1/llm-models/${id}`);
    return response.data;
};

export const updateModelById = async (id: string, data: ModelConfig) => {
    const response = await axiosInstance.patch(`/api/v1/llm-models/${id}`, data);
    return response.data;
};

export const deleteModelById = async (id: string) => {
    const response = await axiosInstance.delete(`/api/v1/llm-models/${id}`);
    return response.data;
};

