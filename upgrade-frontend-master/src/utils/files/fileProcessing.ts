interface CompressionOptions {
  maxWidth?: number;
  maxHeight?: number;
  quality?: number;
  maxSizeKB?: number;
}

export const compressImage = async (
  file: File,
  options: CompressionOptions = {},
): Promise<File> => {
  const {
    maxWidth = 1920,
    maxHeight = 1080,
    quality = 0.8,
    maxSizeKB = 180,
  } = options;

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);

    reader.onload = (event) => {
      const img = new Image();
      img.src = event.target?.result as string;

      img.onload = () => {
        const canvas = document.createElement("canvas");
        let width = img.width;
        let height = img.height;

        // Calculate aspect ratio
        if (width > height) {
          if (width > maxWidth) {
            height = Math.round((height * maxWidth) / width);
            width = maxWidth;
          }
        } else {
          if (height > maxHeight) {
            width = Math.round((width * maxHeight) / height);
            height = maxHeight;
          }
        }

        canvas.width = width;
        canvas.height = height;

        const ctx = canvas.getContext("2d");
        if (!ctx) {
          reject(new Error("Failed to get canvas context"));
          return;
        }

        ctx.drawImage(img, 0, 0, width, height);

        // Function to check file size
        const checkSize = (blob: Blob): boolean => {
          return blob.size <= maxSizeKB * 1024;
        };

        // Function to create file from blob
        const createFile = (blob: Blob): File => {
          return new File([blob], file.name, {
            type: "image/jpeg",
            lastModified: Date.now(),
          });
        };

        // Compress with initial quality
        canvas.toBlob(
          async (blob) => {
            if (!blob) {
              reject(new Error("Failed to create blob"));
              return;
            }

            // If size is already small enough, return
            if (checkSize(blob)) {
              resolve(createFile(blob));
              return;
            }

            // If not, try to compress more
            let currentQuality = quality;
            let currentBlob = blob;

            while (!checkSize(currentBlob) && currentQuality > 0.1) {
              currentQuality -= 0.1;
              currentBlob = await new Promise<Blob>((resolve) => {
                canvas.toBlob(
                  (newBlob) => resolve(newBlob!),
                  "image/jpeg",
                  currentQuality,
                );
              });
            }

            resolve(createFile(currentBlob));
          },
          "image/jpeg",
          quality,
        );
      };

      img.onerror = () => {
        reject(new Error("Failed to load image"));
      };
    };

    reader.onerror = () => {
      reject(new Error("Failed to read file"));
    };
  });
};

export const processImage = async (file: File): Promise<File> => {
  try {
    // Compress image
    const compressed = await compressImage(file);
    return compressed;
  } catch (error) {
    console.error("Error processing image:", error);
    throw error;
  }
};

export const uploadToStorage = async (file: File): Promise<string> => {
  try {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error("Upload failed");
    }

    const data = await response.json();
    return data.url;
  } catch (error) {
    console.error("Upload error:", error);
    throw error;
  }
};

// Helper function to convert File to base64
export const fileToBase64 = (file: File): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const base64String = reader.result as string;
      resolve(base64String);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
};

// Helper function to get file extension
export const getFileExtension = (filename: string): string => {
  return filename.slice(((filename.lastIndexOf(".") - 1) >>> 0) + 2);
};

// Helper function to check if file is an image
export const isImageFile = (file: File): boolean => {
  return file.type.startsWith("image/");
};

// Helper function to format file size
export const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
};
