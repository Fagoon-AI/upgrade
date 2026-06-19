export const compressImage = async (
  file: File,
  maxSizeKB: number = 180,
): Promise<File> => {
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
        const aspectRatio = width / height;

        // Initialize compression quality
        let quality = 0.9;
        let dataUrl: string;

        const compress = () => {
          // Adjust dimensions if needed
          if (width > 1920 || height > 1920) {
            if (aspectRatio > 1) {
              width = 1920;
              height = Math.round(width / aspectRatio);
            } else {
              height = 1920;
              width = Math.round(height * aspectRatio);
            }
          }

          canvas.width = width;
          canvas.height = height;

          const ctx = canvas.getContext("2d");
          if (!ctx) {
            reject(new Error("Could not get canvas context"));
            return;
          }

          ctx.drawImage(img, 0, 0, width, height);

          // Convert to base64 with current quality
          dataUrl = canvas.toDataURL("image/jpeg", quality);

          // Check size
          const sizeKB = Math.round((dataUrl.length * 0.75) / 1024); // base64 size to KB

          if (sizeKB > maxSizeKB && quality > 0.1) {
            // Reduce quality and try again
            quality -= 0.1;
            compress();
          } else {
            // Convert base64 back to File
            const byteString = atob(dataUrl.split(",")[1]);
            const mimeType = dataUrl.split(",")[0].split(":")[1].split(";")[0];
            const ab = new ArrayBuffer(byteString.length);
            const ia = new Uint8Array(ab);

            for (let i = 0; i < byteString.length; i++) {
              ia[i] = byteString.charCodeAt(i);
            }

            const compressedFile = new File([ab], file.name, {
              type: mimeType,
            });
            resolve(compressedFile);
          }
        };

        compress();
      };
      img.onerror = (error) => reject(error);
    };
    reader.onerror = (error) => reject(error);
  });
};
