interface ImageProcessingOptions {
  maxWidth?: number;
  maxHeight?: number;
  quality?: number;
  maxSizeKB?: number;
}

/**
 * Processes and compresses an image file
 */
export const processImage = async (
  file: File,
  options: ImageProcessingOptions = {},
): Promise<{ file: File; base64: string }> => {
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

        // Calculate new dimensions while maintaining aspect ratio
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

        // Convert to base64
        const base64 = canvas.toDataURL("image/jpeg", quality);

        // Convert base64 to File
        fetch(base64)
          .then((res) => res.blob())
          .then((blob) => {
            const processedFile = new File([blob], file.name, {
              type: "image/jpeg",
              lastModified: Date.now(),
            });

            // Check if file size is within limit
            if (processedFile.size > maxSizeKB * 1024) {
              // If still too large, try with lower quality
              const lowerQuality = quality * 0.8;
              if (lowerQuality > 0.1) {
                processImage(file, { ...options, quality: lowerQuality })
                  .then(resolve)
                  .catch(reject);
              } else {
                reject(new Error("Unable to compress image to required size"));
              }
            } else {
              resolve({ file: processedFile, base64 });
            }
          })
          .catch(reject);
      };

      img.onerror = () => reject(new Error("Failed to load image"));
    };

    reader.onerror = () => reject(new Error("Failed to read file"));
  });
};

/**
 * Validates file type and size
 */
export const validateFile = (file: File, maxSizeKB: number = 180): boolean => {
  if (!file.type.startsWith("image/")) {
    throw new Error("File must be an image");
  }

  if (file.size > maxSizeKB * 1024) {
    throw new Error(`File size must be less than ${maxSizeKB}KB`);
  }

  return true;
};

/**
 * Formats file size for display
 */
export const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
};
