import { FaFileAlt, FaFilePdf } from "react-icons/fa";

import { FaFileImage } from "react-icons/fa6";

interface FilePreviewProps {
    file: string;
    onRemove: () => void;
}

export function FilePreview({
    file,
    onRemove,
}: FilePreviewProps) {
    const isLocalPreview = file.startsWith("blob:") || file.startsWith("data:image/");
    
    const extension = isLocalPreview ? "image" : file.split(".").pop()?.toLowerCase();

    const type =
        ["jpg", "jpeg", "png", "gif", "svg"].includes(
            extension || ""
        ) || isLocalPreview
            ? "image"
            : extension;

    return (
        <div className="relative inline-block">
            {isLocalPreview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img 
                    src={file} 
                    alt="Selected attachment" 
                    className="w-12 h-12 object-cover rounded-lg border border-slate-200 dark:border-gray-800 shadow-sm"
                />
            ) : type === "image" ? (
                <FaFileImage className="text-red-400 text-3xl" />
            ) : type === "pdf" ? (
                <FaFilePdf className="text-red-400 text-3xl" />
            ) : (
                <FaFileAlt className="text-red-400 text-3xl" />
            )}

            <button
                onClick={onRemove}
                className="absolute -top-1.5 -right-1.5 bg-black/60 hover:bg-black text-white rounded-full border border-white/20 w-5 h-5 flex items-center justify-center text-xs transition-colors"
            >
                ×
            </button>
        </div>
    );
}