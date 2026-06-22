import axiosInstance from "../axios";

export const getUserPreferences = async () => {
  const response = await axiosInstance.get(`/api/v1/userPreferences`);
  return response.data;
};

export const updateUserPreferences = async (preferences: any) => {
  const response = await axiosInstance.post(`/api/v1/userPreferences`, preferences);
  return response.data;
};
