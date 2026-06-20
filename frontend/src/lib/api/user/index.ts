import axiosInstance from "../axios";

export const getUserPreferences = async () => {
  const response = await axiosInstance.get(`/api/v1/userPreferences`);
  return response.data;
};

export const updateUserPreferences = async (preferences: any) => {
  const response = await axiosInstance.post(`/api/v1/userPreferences`, preferences);
  return response.data;
};

export const getApiKeys = async () => {
  const response = await axiosInstance.get(`/api/v1/apikey`);
  return response.data;
};

export const generateApiKey = async () => {
  const response = await axiosInstance.post(`/api/v1/apikey`, {});
  return response.data;
};

export const checkUserToken = async () => {
  // Using the base URL configured in axiosInstance
  const response = await axiosInstance.get('/user/checkToken');
  return response.data;
};
