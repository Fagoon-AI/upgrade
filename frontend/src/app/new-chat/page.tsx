"use client";
import { useState, useCallback, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import ChatInterface from "@/components/ChatInterface";
import { Message } from "@/types/chat";
import { showErrorToast } from "@/utils/toast";

export default function NewChatPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [internetSearch, setInternetSearch] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const uploadFiles = async (files: File[], type: "pdf" | "image") => {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append("files", file);
    });

    const endpoint = type === "pdf" ? "/api/upload/pdf" : "/api/analyze";

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Failed to upload ${type} files`);
      }

      const data = await response.json();
      return data.paths || [];
    } catch (error) {
      console.error(`${type} upload error:`, error);
      throw error;
    }
  };

  const handleSendMessage = useCallback(
    async (
      content: string,
      files?: File[],
      isRetry: boolean = false,
      isVoice: boolean = false
    ) => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      abortControllerRef.current = new AbortController();
      setIsLoading(true);
      setError(null);

      try {
        let processedContent = content;

        if (files && files.length > 0) {
          const pdfFile = files.find((file) => file.type === "application/pdf");

          if (pdfFile) {
            const formData = new FormData();
            formData.append("document", pdfFile);
            formData.append("prompt", content || "Analyze this PDF");

            const pdfResponse = await fetch("/api/upload/pdf", {
              method: "POST",
              body: formData,
            });

            if (!pdfResponse.ok) {
              throw new Error("Failed to process PDF");
            }

            const pdfData = await pdfResponse.json();
            processedContent = pdfData.response || content;
          }
        }

        const userMessage: Message = {
          id: Date.now().toString(),
          role: "user",
          content: processedContent,
          timestamp: new Date().toISOString(),
        };

        if (!isRetry) {
          setMessages((prev) => [...prev, userMessage]);
        }

        const convo = messages.map((msg) => ({
          role: msg.role,
          content: msg.content,
        }));

        if (!isRetry) {
          convo.push({
            role: "user",
            content: processedContent,
          });
        }

        const requestBody = {
          internet_search: internetSearch,
          convo,
          is_voice: isVoice,
        };

        const response = await fetch("/api/chat", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(requestBody),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.error || "Failed to get response");
        }

        const data = await response.json();

        if (isRetry) {
          setMessages((prev) => prev.slice(0, -1));
        }

        const aiMessage: Message = {
          id: Date.now().toString() + "-ai",
          role: "assistant",
          content: data.response || data.message || data,
          timestamp: new Date().toISOString(),
        };

        setMessages((prev) => [...prev, aiMessage]);

        // Create chat history after first successful message
        if (messages.length === 0 && !isRetry) {
          const historyResponse = await fetch("/api/chat/history", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              messages: [
                ...convo,
                { role: "assistant", content: aiMessage.content },
              ],
            }),
          });

          if (historyResponse.ok) {
            const { id } = await historyResponse.json();
            router.push(`/c/${id}`);
          }
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }
        const errorMessage =
          err instanceof Error ? err.message : "Something went wrong";
        setError(errorMessage);
        showErrorToast(errorMessage);
        console.error("Chat error:", err);
      } finally {
        setIsLoading(false);
        abortControllerRef.current = null;
      }
    },
    [messages, internetSearch, router]
  );

  const handleRegenerate = useCallback(async () => {
    if (messages.length < 2) return;

    const lastUserMessageIndex = [...messages]
      .reverse()
      .findIndex((m) => m.role === "user");
    if (lastUserMessageIndex === -1) return;

    const lastUserMessage =
      messages[messages.length - lastUserMessageIndex - 1];
    await handleSendMessage(lastUserMessage.content, undefined, true);
  }, [messages, handleSendMessage]);

  return (
    <div className="h-screen bg-[#343541]">
      <ChatInterface
        messages={messages}
        onSendMessage={handleSendMessage}
        onRegenerate={handleRegenerate}
        isLoading={isLoading}
        error={error ?? undefined}
        internetSearch={internetSearch}
        setInternetSearch={setInternetSearch}
      />
    </div>
  );
}
