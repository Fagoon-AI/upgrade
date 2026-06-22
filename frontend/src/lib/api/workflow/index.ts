import { CreateWorkflowPayload } from "@/lib/schemas/workflow";
import { GetWorkflowsResponse } from "@/lib/types/workflow";
import axiosInstance from "../axios";

export const createWorkflow = async (workflowData: CreateWorkflowPayload) => {
  const response = await axiosInstance.post(`/api/v1/workflows`, workflowData);
  return response.data;
};

export const getWorkflows = async (skip: number = 0, limit: number = 10): Promise<GetWorkflowsResponse> => {
  const response = await axiosInstance.get(`/api/v1/workflows`, {
    params: { skip, limit }
  });
  return response.data;
};

export const getWorkflowById = async (id: string) => {
  const response = await axiosInstance.get(`/api/v1/workflows/${id}`);
  return response.data;
};

export const updateWorkflowById = async (id: string, data: any) => {
  const response = await axiosInstance.put(`/api/v1/workflows/${id}`, data);
  return response.data;
};

export const getWorkflowVersion = async (id: string) => {
  const response = await axiosInstance.get(`/api/v1/workflows/${id}/versions`);
  return response.data;
};

export const RestoreWorkflowVersion = async (id: string, version_id: string) => {
  const response = await axiosInstance.get(`/api/v1/workflows/${id}/versions/${version_id}/restore`);
  return response.data;
};

//* Workflow API

export const publishWorkflowApi = async (id: string) => {
  const response = await axiosInstance.post(
    `/api/v1/workflows/${id}/publish-api`
  );
  return response.data;
};

export const getWorkflowApiInfo = async (id: string) => {
  const response = await axiosInstance.get(
    `/api/v1/workflows/${id}/api-info`
  );
  return response.data;
};

export const updateWorkflowApi = async (
  id: string,
  data: {
    rate_limit?: number;
    timeout?: number;
    is_active?: boolean;
  }
) => {
  const response = await axiosInstance.patch(
    `/api/v1/workflows/${id}/api`,
    data
  );
  return response.data;
};

export const revokeWorkflowApi = async (id: string) => {
  const response = await axiosInstance.delete(`/api/v1/workflows/${id}/api`);
  return response.data;
};


export const executeWorkflowApi = async (
  slug: string,
  payload: Record<string, any>
) => {
  const response = await axiosInstance.post(
    `/api/v1/workflow-api/${slug}/execute`,
    payload
  );
  return response.data;
};


//* Exections

export const runWorkflow = async (workflowId: string, payload?: any) => {
  const response = await axiosInstance.post(
    `/api/v1/executions/${workflowId}/run`,
    payload
  );
  return response.data;
};

export const getExecutionStatus = async (executionId: string) => {
  const response = await axiosInstance.get(
    `/api/v1/executions/${executionId}/status`
  );
  return response.data;
};

export const cancelExecution = async (executionId: string) => {
  const response = await axiosInstance.post(
    `/api/v1/executions/${executionId}/cancel`
  );
  return response.data;
};

export const resumeExecution = async (executionId: string) => {
  const response = await axiosInstance.post(
    `/api/v1/executions/${executionId}/resume`
  );
  return response.data;
};

export const retryExecution = async (executionId: string) => {
  const response = await axiosInstance.post(
    `/api/v1/executions/${executionId}/retry`
  );
  return response.data;
};

export const getBulkExecutionStatus = async (executionIds: string[]) => {
  const response = await axiosInstance.post(
    `/api/v1/executions/bulk/status`,
    { execution_ids: executionIds }
  );
  return response.data;
};

export const getExecutionTimeline = async (executionId: string) => {
  const response = await axiosInstance.get(
    `/api/v1/executions/${executionId}/timeline`
  );
  return response.data;
};

export const getNodeTraceDetail = async (traceId: string) => {
  const response = await axiosInstance.get(
    `/api/v1/executions/node-trace/${traceId}`
  );
  return response.data;
};

export const getExecutions = async () => {
  const response = await axiosInstance.get(`/api/v1/executions`);
  return response.data;
};


//* Nodes

export const getNodesRegistry = async () => {
  const response = await axiosInstance.get(`/api/v1/nodes/registry`);
  return response.data;
};

export const getNodesCategories = async () => {
  const response = await axiosInstance.get(`/api/v1/nodes/registry/categories`);
  return response.data;
};

export const searchNode = async (params: { q: string, category: string }) => {
  const response = await axiosInstance.get(`/api/v1/nodes/registry/search`, { params });
  return response.data;
};

export const getNodeDetails = async (node_type: string) => {
  const response = await axiosInstance.get(`/api/v1/nodes/registry/${node_type}`,);
  return response.data;
};

export const getNodeSchema = async (node_type: string) => {
  const response = await axiosInstance.get(`/api/v1/nodes/registry/${node_type}`,);
  return response.data;
};

export const getFileUrl = async (filePath: string) => {
  const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || "";
  const finalUrl = baseUrl ? `${baseUrl.replace(/\/$/, '')}/${filePath.replace(/^\//, '')}` : `/${filePath.replace(/^\//, '')}`;
  return { success: true, data: finalUrl };
};

export const publishWorkflow = async (workflowId: string) => {
  const response = await axiosInstance.post(`/api/v1/workflows/${workflowId}/publish`);
  return response.data;
};
