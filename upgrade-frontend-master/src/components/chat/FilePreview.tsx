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
    const extension =
        file.split(".").pop()?.toLowerCase();

    const type =
        ["jpg", "jpeg", "png", "gif", "svg"].includes(
            extension || ""
        )
            ? "image"
            : extension;

    return (
        <div className="relative">
            {type === "image" ? (
                <FaFileImage className="text-red-400 text-3xl" />
            ) : type === "pdf" ? (
                <FaFilePdf className="text-red-400 text-3xl" />
            ) : (
                <FaFileAlt className="text-red-400 text-3xl" />
            )}

            <button
                onClick={onRemove}
                className=" absolute -top-1 -right-1 rounded-full border px-1 text-xs "
            >
                ×
            </button>
        </div>
    );
}