import { useState, useCallback } from "react";
import * as uploadApi from "@/lib/api/upload";

interface FileUploadOptions {
  maxSize?: number;
  acceptedTypes?: string[];
  onUploadComplete?: (urls: string[]) => void;
  onError?: (error: string) => void;
}

export const useFileUpload = (options: FileUploadOptions = {}) => {
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  const {
    maxSize = 5 * 1024 * 1024, // 5MB default
    acceptedTypes = ["image/*", ".pdf"],
    onUploadComplete,
    onError,
  } = options;

  const validateFile = useCallback(
    (file: File): boolean => {
      if (file.size > maxSize) {
        onError?.(
          `File ${file.name} is too large. Maximum size is ${maxSize / 1024 / 1024}MB`,
        );
        return false;
      }

      const isValidType = acceptedTypes.some((type) => {
        if (type.includes("/*")) {
          const [baseType] = type.split("/");
          return file.type.startsWith(baseType);
        }
        return file.type === type || file.name.endsWith(type);
      });

      if (!isValidType) {
        onError?.(`File ${file.name} is not a supported type`);
        return false;
      }

      return true;
    },
    [maxSize, acceptedTypes, onError],
  );

  const addFiles = useCallback(
    (newFiles: File[]) => {
      const validFiles = newFiles.filter(validateFile);
      setFiles((prev) => [...prev, ...validFiles]);
    },
    [validateFile],
  );

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const uploadFiles = useCallback(async (): Promise<string[]> => {
    if (files.length === 0) return [];

    setUploading(true);
    setProgress(0);

    try {
      const uploadPromises = files.map(async (file, index) => {
        const formData = new FormData();
        formData.append("file", file);

        const response = await uploadApi.uploadGeneral(formData);

        setProgress(((index + 1) / files.length) * 100);
        return response.url;
      });

      const urls = await Promise.all(uploadPromises);
      onUploadComplete?.(urls);
      setFiles([]);
      return urls;
    } catch (error) {
      onError?.(error instanceof Error ? error.message : "Upload failed");
      throw error;
    } finally {
      setUploading(false);
      setProgress(0);
    }
  }, [files, onUploadComplete, onError]);

  const clearFiles = useCallback(() => {
    setFiles([]);
  }, []);

  return {
    files,
    uploading,
    progress,
    addFiles,
    removeFile,
    uploadFiles,
    clearFiles,
  };
};
