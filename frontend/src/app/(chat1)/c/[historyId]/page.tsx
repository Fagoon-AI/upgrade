"use client";

import { useParams } from "next/navigation";
import React, { useEffect, useRef, useState } from "react";
import ChatInput from "@/components/chat/chat-input";
import { Button } from "@/components/ui/button";
import { ChevronLeft, Loader2, ArrowDown, Bot } from "lucide-react";
import ChatMessageOutput from "@/components/chat/chat-message";
import { useConversationHistory, useSendMessage, useUpgradeChat } from "../../hooks/useUpgradeChat";
import { Loader } from "@/components/ui/loader";


const ChatPage = () => {
    const params = useParams<{ historyId: string }>();
    const historyId = params?.historyId;

    const sendMessage = useSendMessage();
    const { activeStatus, isLoading: contextIsLoading } = useUpgradeChat();

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const [showScrollButton, setShowScrollButton] = useState(false);
    const [isWaitingForResponse, setIsWaitingForResponse] = useState(false);

    const { data, isLoading: conversationLoading } = useConversationHistory(historyId);

    const messages = React.useMemo(() => {
        return data?.data?.messages.map((item: any) => ({
            role: item.role,
            message: {
                data: item.content,
                metadata: item.metadata,
            },
        })) ?? [];
    }, [data?.data?.messages]);

    const isLoading = sendMessage.isPending || contextIsLoading;
    const isThinking = isLoading || isWaitingForResponse;
    const [dotCount, setDotCount] = useState(1);

    useEffect(() => {
        if (!isThinking) {
            setDotCount(1);
            return;
        }

        const interval = window.setInterval(() => {
            setDotCount((count) => (count === 3 ? 1 : count + 1));
        }, 400);

        return () => window.clearInterval(interval);
    }, [isThinking]);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({
            behavior: "smooth",
        });
    };

    const handleScroll = () => {
        if (!scrollContainerRef.current) return;
        const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
        const isNearBottom = scrollHeight - scrollTop - clientHeight < 150;
        setShowScrollButton(!isNearBottom);
    };

    const prevLengthRef = useRef(0);
    useEffect(() => {
        const currentLength = messages.length;
        if (currentLength > prevLengthRef.current || isThinking) {
            scrollToBottom();
        }
        prevLengthRef.current = currentLength;
    }, [messages.length, isThinking]);

    // De-assert waiting state once the assistant response renders on the timeline
    useEffect(() => {
        if (messages.length > 0) {
            const lastMsg = messages[messages.length - 1];
            if (lastMsg.role === "assistant") {
                setIsWaitingForResponse(false);
            }
        }
    }, [messages]);

    const handleSubmitInput = async (text: string, fileData?: string | null, fileName?: string | null) => {
        if (!text || !historyId) return;

        setIsWaitingForResponse(true);
        await sendMessage.mutateAsync({
            conversationId: historyId,
            message: text,
            file_data: fileData,
            file_name: fileName,
        });
        scrollToBottom();
    };

    if (!historyId) return null;

    return (
        <div className="relative flex flex-col h-[100dvh]">
            {/* Header */}
            <div className="z-10 backdrop-blur-sm border-b shrink-0">
                <div className="max-w-5xl mx-auto px-4 py-3 md:py-2 flex items-center">
                    <Button variant="ghost" size="icon" className="mr-2">
                        <ChevronLeft className="h-5 w-5" />
                    </Button>

                    <h1 className="text-lg font-medium truncate">
                        Chat
                    </h1>
                </div>
            </div>

            {/* Messages */}
            <div
                className="flex-1 overflow-y-auto p-4"
                ref={scrollContainerRef}
                onScroll={handleScroll}
            >
                {conversationLoading && !isThinking ? (
                    <Loader size="md" text="Loading conversation history..." />
                ) : (
                    <>
                        <div className="max-w-4xl mx-auto space-y-4 pb-10">
                            {messages.map((msg: any, index: number) => {
                                if (isThinking && index === messages.length - 1 && msg.role === "assistant") {
                                    return null;
                                }
                                return (
                                    <div key={index}>
                                        <ChatMessageOutput msg={msg} />
                                    </div>
                                )
                            })}
                        </div>
                        {isThinking && (
                            <div className="max-w-4xl mx-auto mb-4 flex w-full justify-start">
                                <div className="flex max-w-[85%] flex-row gap-2">
                                    <div className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center dark:text-white text-black">
                                        <Bot size={14} />
                                    </div>
                                    <div className="flex flex-col gap-1.5 min-w-0">
                                        <div className="flex items-center text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                                            <Loader2 className="h-4 w-4 animate-spin mr-2" />
                                            <span>{activeStatus || `Thinking${".".repeat(dotCount)}`}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}
                    </>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Scroll to Bottom Floating Button */}
            {showScrollButton && (
                <div className="absolute bottom-[150px] left-1/2 -translate-x-1/2 z-50">
                    <Button
                        variant="secondary"
                        size="icon"
                        className="rounded-full shadow-md border border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-black/80 backdrop-blur-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-900"
                        onClick={scrollToBottom}
                    >
                        <ArrowDown className="h-5 w-5" />
                    </Button>
                </div>
            )}

            {/* Input */}
            <div className="shrink-0 z-10 pt-4">
                <ChatInput
                    history_id={historyId}
                    handleSubmitInput={handleSubmitInput}
                />
            </div>
        </div >
    );
};

export default ChatPage;