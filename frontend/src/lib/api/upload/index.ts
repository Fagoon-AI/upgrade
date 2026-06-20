import axiosInstance from "../axios";

export const uploadChatFile = async (formData: FormData) => {
  const response = await axiosInstance.post('/api/chat/upload-file', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const uploadPdf = async (formData: FormData) => {
  const response = await axiosInstance.post('/api/upload/pdf', formData, {
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

export const uploadToGcp = async (formData: FormData) => {
    const response = await axiosInstance.post('/api/workflow/upload-to-gcp', formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
    });
    return response.data;
}

export const externalGptUpload = async (formData: FormData) => {
  const response = await axiosInstance.post('/gpt/api/v2/fagoongpt/', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};
