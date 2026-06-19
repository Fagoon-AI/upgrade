import { useState, useRef, useEffect, useCallback } from "react";
import { Message } from "@/types/chat";
import Image from "next/image";
import { IoSend } from "react-icons/io5";
import { FiRefreshCcw } from "react-icons/fi";
import { BsMicFill, BsFillMicMuteFill } from "react-icons/bs";
import { AiOutlinePicture } from "react-icons/ai";
import { HiDocument } from "react-icons/hi";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import parse from "html-react-parser";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/cjs/styles/prism";
import { showSuccessToast, showErrorToast } from "@/utils/toast";

interface ChatInterfaceProps {
  messages: Message[];
  onSendMessage: (
    content: string,
    files?: File[],
    isAIResponse?: boolean
  ) => Promise<void>;
  onRegenerate: () => Promise<void>;
  isLoading?: boolean;
  error?: string;
  internetSearch?: boolean;
  setInternetSearch?: (value: boolean) => void;
}
// Custom components for ReactMarkdown
const MarkdownComponents = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  code({ node, inline, className, children, ...props }: any) {
    const language = className?.replace("language-", "") ?? "";
    return !inline ? (
      <SyntaxHighlighter
        style={oneDark}
        language={language}
        customStyle={{
          margin: "1rem 0",
          borderRadius: "6px",
          padding: "1rem",
        }}
        {...props}
      >
        {String(children).replace(/\n$/, "")}
      </SyntaxHighlighter>
    ) : (
      <code className="bg-gray-800 rounded px-1" {...props}>
        {children}
      </code>
    );
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  p({ children }: any) {
    return <p className="mb-2 last:mb-0">{children}</p>;
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ul({ children }: any) {
    return <ul className="list-disc ml-4 mb-2">{children}</ul>;
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ol({ children }: any) {
    return <ol className="list-decimal ml-4 mb-2">{children}</ol>;
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  li({ children }: any) {
    return <li className="mb-1">{children}</li>;
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  a({ href, children }: any) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-blue-400 hover:underline"
      >
        {children}
      </a>
    );
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  table({ children }: any) {
    return (
      <div className="overflow-x-auto my-2">
        <table className="border-collapse border border-gray-600 w-full">
          {children}
        </table>
      </div>
    );
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  th({ children }: any) {
    return (
      <th className="border border-gray-600 px-4 py-2 bg-gray-800">
        {children}
      </th>
    );
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  td({ children }: any) {
    return <td className="border border-gray-600 px-4 py-2">{children}</td>;
  },
};

const MessageContent = ({ content }: { content: string }) => {
  // Function to determine if content is HTML
  const isHTML = (str: string) => {
    const doc = new DOMParser().parseFromString(str, "text/html");
    return Array.from(doc.body.childNodes).some((node) => node.nodeType === 1);
  };

  return isHTML(content) ? (
    <div className="markdown-content">
      {parse(content, {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        replace: (domNode: any) => {
          if (domNode.type === "tag" && domNode.name === "pre") {
            // Handle code blocks in HTML
            const code = domNode.children[0]?.children?.[0]?.data;
            const language =
              domNode.children[0]?.attribs?.class?.replace("language-", "") ||
              "text";

            return (
              <SyntaxHighlighter
                language={language}
                style={oneDark}
                customStyle={{
                  margin: "1rem 0",
                  borderRadius: "6px",
                  padding: "1rem",
                }}
              >
                {code}
              </SyntaxHighlighter>
            );
          }
        },
      })}
    </div>
  ) : (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>
      {content}
    </ReactMarkdown>
  );
};

// Updated MessageBubble component
const MessageBubble = ({ message }: { message: Message }) => (
  <div
    className={`border-b border-black/10 ${
      message.role === "assistant" ? "bg-[#444654]" : ""
    }`}
  >
    <div className="max-w-3xl mx-auto px-4 py-6 flex">
      <div className="w-[30px] h-[30px] relative mr-4 flex-shrink-0">
        <Image
          src={
            message.role === "user"
              ? "/upgrade-profile-default.jpg"
              : "/Icon.svg"
          }
          alt={message.role}
          fill
          className="rounded-sm object-cover"
        />
      </div>
      <div className="flex-1 text-white overflow-x-auto">
        <MessageContent content={message.content} />
        
        {/* Render Metadata Items (like generated images) */}
        {message.metadata?.data && message.metadata.data.length > 0 && (
          <div className="mt-4 flex flex-col gap-4">
            {message.metadata.data.map((item, index) => {
              if (item.type === "generated_image" && typeof item.data === "object" && item.data !== null) {
                const imgData = item.data as {
                  url: string;
                  db_id: string;
                  prompt: string;
                  summary: string;
                  asset_type: string;
                };
                const imgUrl = imgData.url ? (imgData.url.startsWith("http://") || imgData.url.startsWith("https://") ? imgData.url : `${process.env.NEXT_PUBLIC_BASE_URL || process.env.NEXT_PUBLIC_API_URL || ""}${imgData.url.startsWith("/") ? "" : "/"}${imgData.url}`) : "";
                return (
                  <div key={index} className="rounded-lg overflow-hidden border border-gray-600 bg-gray-800/50 max-w-lg">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={imgUrl}
                      alt={imgData.summary || "Generated Image"}
                      className="w-full h-auto object-cover"
                    />
                    {imgData.summary && (
                      <div className="p-3 text-sm text-gray-300 italic border-t border-gray-600">
                        {imgData.summary}
                      </div>
                    )}
                  </div>
                );
              }

              if (item.type === "generated_video" && typeof item.data === "object" && item.data !== null) {
                const videoData = item.data as {
                  url: string;
                  db_id: string;
                  prompt: string;
                  summary: string;
                  asset_type: string;
                };
                const videoUrl = videoData.url ? (videoData.url.startsWith("http://") || videoData.url.startsWith("https://") ? videoData.url : `${process.env.NEXT_PUBLIC_BASE_URL || process.env.NEXT_PUBLIC_API_URL || ""}${videoData.url.startsWith("/") ? "" : "/"}${videoData.url}`) : "";
                return (
                  <div key={index} className="rounded-lg overflow-hidden border border-gray-600 bg-gray-800/50 max-w-lg">
                    <video
                      src={videoUrl}
                      controls
                      className="w-full h-auto"
                    />
                    {videoData.summary && (
                      <div className="p-3 text-sm text-gray-300 italic border-t border-gray-600">
                        {videoData.summary}
                      </div>
                    )}
                  </div>
                );
              }
              return null;
            })}
          </div>
        )}
      </div>
    </div>
  </div>
);

const ChatInterface = ({
  messages,
  onSendMessage,
  onRegenerate,
  isLoading = false,
  error,
  internetSearch = false,
  setInternetSearch,
}: ChatInterfaceProps) => {
  const [input, setInput] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(
    null
  );
  const [isProcessingFile, setIsProcessingFile] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);

  const [isUploading, setIsUploading] = useState(false);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    try {
      await onSendMessage(input.trim());
      setInput("");
    } catch (error) {
      showErrorToast("Failed to send message");
      console.error("Error sending message:", error);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handlePdfUpload = async (file: File) => {
    const formData = new FormData();
    formData.append("document", file);
    formData.append("prompt", "Analyze this PDF"); // You can customize the prompt

    try {
      const response = await fetch("/api/upload/pdf", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Failed to process PDF");
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error("PDF processing error:", error);
      throw error;
    }
  };

  const handleFileUpload = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    const file = files[0];
    setIsProcessingFile(true);

    try {
      if (file.type === "application/pdf") {
        const formData = new FormData();
        formData.append("document", file);
        formData.append(
          "prompt",
          "Please analyze this document and provide a detailed summary."
        );

        const response = await fetch("/api/chat", {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          throw new Error("Failed to process PDF");
        }

        const data = await response.json();

        // Add user message about the upload
        await onSendMessage(`Analyzing PDF: ${file.name}`);

        // Add AI response with the analysis
        if (data.response) {
          await onSendMessage(data.response, undefined, true); // true indicates it's an AI response
        }
      } else if (file.type.startsWith("image/")) {
        showErrorToast("Image processing not implemented yet");
        return;
      } else {
        showErrorToast("Unsupported file type");
        return;
      }

      // Reset file input
      event.target.value = "";
    } catch (error) {
      showErrorToast("Failed to process file");
      console.error("File processing error:", error);
    } finally {
      setIsProcessingFile(false);
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const audioChunks: BlobPart[] = [];

      recorder.ondataavailable = (event) => {
        audioChunks.push(event.data);
      };

      recorder.onstop = async () => {
        try {
          const audioBlob = new Blob(audioChunks, { type: "audio/wav" });
          const formData = new FormData();
          formData.append("audio", audioBlob, "audio-message.wav");

          const response = await fetch("/api/chat", {
            method: "POST",
            body: formData,
          });

          if (!response.ok) {
            throw new Error("Failed to transcribe audio");
          }

          const data = await response.json();
          if (data.text) {
            await onSendMessage(data.text);
          }
        } catch (error) {
          showErrorToast("Failed to process audio");
          console.error("Audio processing error:", error);
        } finally {
          stream.getTracks().forEach((track) => track.stop());
        }
      };

      recorder.start();
      setMediaRecorder(recorder);
      setIsRecording(true);
      showSuccessToast("Recording started");
    } catch (error) {
      showErrorToast("Failed to start recording");
      console.error("Error starting recording:", error);
    }
  };

  const stopRecording = () => {
    if (mediaRecorder && isRecording) {
      mediaRecorder.stop();
      setIsRecording(false);
      setMediaRecorder(null);
      showSuccessToast("Recording stopped");
    }
  };

  const handleRegenerate = async () => {
    // Implement regenerate functionality
    console.log("Regenerating response...");
    showSuccessToast("Response regenerated successfully");
  };

  return (
    <div className="flex flex-col h-screen bg-[#343541]">
      {/* Messages Container */}
      <div className="flex-1 overflow-y-auto">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {(isLoading || isProcessingFile) && (
          <div className="border-b border-black/10 bg-[#444654]">
            <div className="max-w-3xl mx-auto px-4 py-6 flex">
              <div className="w-[30px] h-[30px] relative mr-4">
                <Image
                  src="/Icon.svg"
                  alt="AI"
                  fill
                  className="rounded-sm object-cover"
                />
              </div>
              <div className="flex-1">
                <div className="animate-pulse">
                  <div className="h-4 bg-gray-600 rounded w-3/4"></div>
                  <div className="space-y-3 mt-4">
                    <div className="h-4 bg-gray-600 rounded"></div>
                    <div className="h-4 bg-gray-600 rounded w-5/6"></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Form */}
      <div className="border-t border-white/20 bg-[#343541] py-4">
        <div className="max-w-3xl mx-auto px-4">
          {/* Internet Search Toggle */}
          {setInternetSearch && (
            <div className="mb-4 flex items-center">
              <label className="flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={internetSearch}
                  onChange={(e) => setInternetSearch(e.target.checked)}
                  className="form-checkbox h-5 w-5 text-blue-600 rounded border-gray-400 bg-[#40414f]"
                />
                <span className="ml-2 text-white text-sm">
                  Enable internet search
                </span>
              </label>
            </div>
          )}

          <form onSubmit={handleSubmit} className="relative">
            <div className="flex items-center space-x-2">
              {/* File Upload Buttons */}
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileUpload}
                accept="image/*"
                className="hidden"
              />
              <input
                type="file"
                ref={pdfInputRef}
                onChange={handleFileUpload}
                accept=".pdf"
                className="hidden"
              />

              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-gray-700"
                disabled={isLoading || isProcessingFile || isRecording}
              >
                <AiOutlinePicture size={20} />
              </button>

              <button
                type="button"
                onClick={() => pdfInputRef.current?.click()}
                className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-gray-700"
                disabled={isLoading || isProcessingFile || isRecording}
              >
                <HiDocument size={20} />
              </button>

              <button
                type="button"
                onClick={isRecording ? stopRecording : startRecording}
                className={`p-2 rounded-lg hover:bg-gray-700 ${
                  isRecording
                    ? "text-red-500"
                    : "text-gray-400 hover:text-white"
                }`}
                disabled={isLoading || isProcessingFile}
              >
                {isRecording ? (
                  <BsFillMicMuteFill size={20} />
                ) : (
                  <BsMicFill size={20} />
                )}
              </button>

              {/* Text Input */}
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
                placeholder="Send a message..."
                className="flex-1 p-2 bg-[#40414f] rounded-lg text-white placeholder-gray-400 focus:outline-none resize-none"
                style={{ maxHeight: "200px", minHeight: "44px" }}
                disabled={isLoading || isRecording || isProcessingFile}
              />

              {/* Send Button */}
              <button
                type="submit"
                disabled={
                  isLoading || !input.trim() || isRecording || isProcessingFile
                }
                className={`p-2 rounded-lg ${
                  isLoading || !input.trim() || isRecording || isProcessingFile
                    ? "text-gray-400 cursor-not-allowed"
                    : "text-white hover:bg-gray-700"
                }`}
              >
                <IoSend size={20} />
              </button>
            </div>
          </form>

          {messages.length > 0 && (
            <div className="mt-4 flex justify-center">
              <button
                onClick={onRegenerate}
                className="flex items-center gap-2 text-sm text-gray-400 hover:text-white"
                disabled={isLoading || isProcessingFile || isRecording}
              >
                <FiRefreshCcw size={16} />
                Regenerate response
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;
