import axiosInstance from "../axios";

export const uploadChatFile = async (formData: FormData) => {
  const response = await axiosInstance.post('/api/chat/upload-file', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const uploadGeneral = async (formData: FormData) => {
  const response = await axiosInstance.post('/api/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};
