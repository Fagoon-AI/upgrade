'use client'

import { IAgentResponseType } from '@/app/agents/[agentId]/chat/[chatId]/types'
import { useSelectedModelContext } from '@/contexts/SelectedModelContext'
import { useWebSocket } from '@/lib/hooks/useWebSocket'
import * as chatApi from '@/lib/api/chat'
import { createContext, useContext, useState, ReactNode } from 'react'
import { showErrorToast } from "@/utils/toast"
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Message } from '@/lib/libs/messages'

type ChatContextType = {
    inputText: string
    chatTitle: string
    setInputText: (value: string) => void
    firstText: string | undefined,
    setFirstText: (value: string | undefined) => void
    isLoading: boolean
    setIsLoading: (value: boolean) => void
    isStreaming: boolean
    setIsStreaming: (value: boolean) => void
    internetSearchEnabled: boolean
    setInternetSearchEnabled: (value: boolean) => void
    assignmentMode: boolean
    setAssignmentMode: (value: boolean) => void
    browserMode: boolean
    setBrowserMode: (value: boolean) => void
    isEnhancingPrompt: boolean
    enhancePrompt: (prompt: string) => Promise<void>
    stopResponse: () => void
    messages: Message[]
    setMessages: (messages: Message[]) => void
    handleNewMessage: (message: string, params?: string) => Promise<void>
    resetChat: () => void
    fetchConversations: (id: string) => Promise<void>
    getChatTitle: (id: string) => Promise<void>
    activeStatus: string | null
    setActiveStatus: (status: string | null) => void
}

const ChatContext = createContext<ChatContextType | undefined>(undefined)

export const useConversationHistory = (conversationId?: string) => {
    return useQuery({
        queryKey: ["conversation", conversationId],
        queryFn: () => chatApi.getUpgradeChatHistory(conversationId!),
        enabled: !!conversationId,
        staleTime: 1000 * 60 * 60, // 1 hour staleTime to prevent wiping local stream cache
        refetchOnWindowFocus: false,
    });
};

export const useSendMessage = () => {

    const {
        internetSearchEnabled,
        browserMode,
        assignmentMode,
        setActiveStatus,
        setIsLoading,
    } = useUpgradeChat();

    const { selectedModel } = useSelectedModelContext();

    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({
            conversationId,
            message,
            generate_audio = false,
        }: {
            conversationId: string;
            message: string;
            generate_audio?: boolean,
        }) => {
            setIsLoading(true);
            setActiveStatus(null);
            const res = await chatApi.streamUpgradeChat({
                conversation_id: conversationId,
                message,
                internet_search: internetSearchEnabled,
                selected_model: selectedModel,
                web_search_enabled: browserMode,
                generate_audio,
            });

            if (!res.ok) {
                setIsLoading(false);
                const errorText = await res.text().catch(() => "");
                throw new Error(`Stream request failed: ${res.status} ${res.statusText} ${errorText}`);
            }

            const reader = res.body?.getReader();
            const decoder = new TextDecoder();
            let currentData = "";
            let currentLogs = "";
            let currentToolSelection = "";
            let currentImage = "";
            let buffer = "";
            if (reader) {
                try {
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        if (value) {
                            buffer += decoder.decode(value, { stream: true });
                            const lines = buffer.split('\n');
                            
                            // Keep the last partial line in the buffer
                            buffer = lines.pop() || "";

                            for (const line of lines) {
                                try {
                                    const cleanLine = line.replace(/^data:\s*/, "").trim();
                                    if (!cleanLine) continue;

                                    const parsed = JSON.parse(cleanLine);

                                    if (parsed.type === "status") {
                                        currentLogs += parsed.data + "\n";
                                        setActiveStatus(parsed.data);
                                    } else if (parsed.type === "llm_response") {
                                        currentData += parsed.data;
                                    } else if (parsed.type === "tool_selection") {
                                        currentToolSelection += parsed.data + "\n";
                                    } else if (parsed.type === "image") {
                                        currentImage += parsed.data + "\n";
                                    } else if (parsed.type === "error") {
                                        currentData += `\n\n **Error:** ${parsed.data}`;
                                    }
                                } catch (e) {
                                    // ignore invalid/incomplete chunks
                                }
                            }

                            // Update query cache progressively
                            queryClient.setQueryData(
                                ["conversation", conversationId],
                                (old: any) => {
                                    if (!old) return old;
                                    const prevMessages = old.data?.messages ?? [];
                                    const newMessages = [...prevMessages];
                                    
                                    if (newMessages.length > 0 && newMessages[newMessages.length - 1].role === "assistant") {
                                        newMessages[newMessages.length - 1] = {
                                            ...newMessages[newMessages.length - 1],
                                            content: currentData,
                                            logs: currentLogs,
                                            toolSelection: currentToolSelection,
                                            image: currentImage
                                        };
                                    }

                                    return {
                                        ...old,
                                        data: {
                                            ...old.data,
                                            messages: newMessages,
                                        },
                                    };
                                }
                            );
                        }
                    }
                } finally {
                    reader.releaseLock();
                }
            }

            return res;
        },
        onSuccess: (_, variables) => {
            setIsLoading(false);
            queryClient.invalidateQueries({
                queryKey: ["conversation", variables.conversationId],
            });
        },
        onError: () => {
            setIsLoading(false);
        },
        onSettled: () => {
            setIsLoading(false);
        },
        onMutate: async ({ conversationId, message }) => {
            await queryClient.cancelQueries({
                queryKey: ["conversation", conversationId],
            });

            const previous = queryClient.getQueryData([
                "conversation",
                conversationId,
            ]);

            queryClient.setQueryData(
                ["conversation", conversationId],
                (old: any) => {
                    const prevMessages = old?.data?.messages ?? [];

                    return {
                        ...old,
                        data: {
                            ...old?.data,
                            messages: [
                                ...prevMessages,
                                {
                                    role: "user",
                                    content: message,
                                },
                                {
                                    role: "assistant",
                                    content: "",
                                    logs: "",
                                    toolSelection: "",
                                    image: ""
                                }
                            ],
                        },
                    };
                }
            );

            return { previous };
        }
    });
};

export const useDeleteChat = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: string) => {
            const res = chatApi.deleteUpgradeConversation(id);

            return res;
        },

        onSuccess: () => {
            queryClient.invalidateQueries({
                queryKey: ["conversations"],
            });
            queryClient.invalidateQueries({
                queryKey: ["chat-ids"],
            });
        },
    });
};


export const ChatProvider = ({ children }: { children: ReactNode }) => {
    const [inputText, setInputText] = useState<string>('')
    const [firstText, setFirstText] = useState<string | undefined>('')
    const [messages, setMessages] = useState<Message[]>([])
    const [isLoading, setIsLoading] = useState<boolean>(false)
    const [isStreaming, setIsStreaming] = useState<boolean>(false)
    const [internetSearchEnabled, setInternetSearchEnabled] = useState(false);
    const [assignmentMode, setAssignmentMode] = useState(false);
    const [browserMode, setBrowserMode] = useState(false);
    const [isEnhancingPrompt, setIsEnhancingPrompt] = useState(false);
    const [chatTitle, setChatTitle] = useState('New Chat...')
    const [controller, setController] = useState<AbortController | null>(null);
    const [activeStatus, setActiveStatus] = useState<string | null>(null);
    const { selectedModel } = useSelectedModelContext()
    const { streamSocketMessage } = useWebSocket()
    const stopResponse = () => {
        if (controller) {
            controller.abort();
            setIsStreaming(false);
        }
    };
    const resetChat = () => {
        setInputText('')
        setMessages([])
        setIsLoading(false)
        setIsStreaming(false)
        setChatTitle('New Chat..')
        setActiveStatus(null)
    }
    const handleNewMessage = async (message: string, params?: string) => {
        setMessages(prev => [...prev, { role: 'user', message: { data: message } }])
        setIsLoading(true)
        const tempMessage: Message = {
            role: "assistant",
            message: {
                data: '',
                logs: ''
            }
        }
        setMessages(prev => [...prev, tempMessage])
        if (assignmentMode) {
            const payload = {
                // conversation_id: '2',
                task: inputText,
                report_type: "research_report",
                report_source: "web",
                tone: "Objective",
                query_domains: []
            };

            const msgToSend = 'start ' + JSON.stringify(payload);

            streamSocketMessage(msgToSend, (chunk) => {
                try {
                    setIsLoading(true);
                    setIsStreaming(true);

                    const parsed = JSON.parse(chunk);
                    const { type, output, status } = parsed;
                    console.log(parsed)
                    if (type == 'logs' && output) {
                        setMessages((prevMessages) => {
                            const newMessages = [...prevMessages];
                            const lastMessage = newMessages[newMessages.length - 1];

                            if (lastMessage?.message?.logs != null) {
                                lastMessage.message.logs += output + '\n';
                            } else {
                                lastMessage.message.logs = output + '\n';
                            }

                            return newMessages;
                        });
                    }

                    if (type == 'report') {
                        // Append only the new part of report data

                        setMessages((prevMessages) => {
                            const newMessages = [...prevMessages];
                            const lastMessage = newMessages[newMessages.length - 1];

                            lastMessage.message.data += output;

                            return newMessages;
                        });
                    }

                    if (type === 'complete' || output === '[DONE]' || status === 'complete') {
                        console.log('✅ End of stream detected');
                        setIsLoading(false);
                        setIsStreaming(false);
                    }
                } catch (err) {
                    console.warn('[WebSocket] ⚠️ Failed to parse chunk:', chunk);
                }
            });
            return;
        }

        if (browserMode) {
            const payload = {
                task: inputText,
                mode: "browser_agent"
            };

            const msgToSend = 'start ' + JSON.stringify(payload);

            streamSocketMessage(msgToSend, (chunk) => {
                try {
                    setIsLoading(true);
                    setIsStreaming(true);

                    const parsed = JSON.parse(chunk);
                    const { type, output, status } = parsed;
                    console.log(parsed)
                    if (type == 'logs' && output) {
                        setMessages((prevMessages) => {
                            const newMessages = [...prevMessages];
                            const lastMessage = newMessages[newMessages.length - 1];

                            if (lastMessage?.message?.logs != null) {
                                lastMessage.message.logs += output + '\n';
                            } else {
                                lastMessage.message.logs = output + '\n';
                            }

                            return newMessages;
                        });
                    }

                    if (type == 'report') {
                        setMessages((prevMessages) => {
                            const newMessages = [...prevMessages];
                            const lastMessage = newMessages[newMessages.length - 1];
                            lastMessage.message.data += output;
                            return newMessages;
                        });
                    }

                    if (type === 'complete' || output === '[DONE]' || status === 'complete') {
                        console.log('✅ End of stream detected');
                        setIsLoading(false);
                        setIsStreaming(false);
                    }
                } catch (err) {
                    console.warn('[WebSocket] ⚠️ Failed to parse chunk:', chunk);
                }
            });
            return;
        } else {
            try {
                const abortController = new AbortController();
                setController(abortController);
                setIsStreaming(true);

                const apiPayload = {
                    conversation_id: params,
                    message,
                    internet_search: internetSearchEnabled,
                    selected_model: selectedModel,
                    web_search_enabled: false,
                    generate_audio: false,
                };

                const response = await chatApi.streamUpgradeChat(apiPayload, abortController.signal)

                const reader = response.body?.getReader()
                const decoder = new TextDecoder()
                let done = false


                let currentData = ""
                let currentLogs = ""
                let currentToolSelection = ""
                let currentImage = ""
                while (reader && !done) {
                    const { value, done: streamDone } = await reader.read()
                    done = streamDone
                    if (value) {
                        const chunkText = decoder.decode(value, { stream: true })
                        const lines = chunkText.split('\n').filter(Boolean)
                        for (const line of lines) {
                            try {
                                const cleanLine = line.replace(/^data:\s*/, "").trim();

                                if (!cleanLine) continue;

                                const parsed = JSON.parse(cleanLine) as {
                                    type: IAgentResponseType;
                                    data: string;
                                };

                                if (parsed.type === "status") {
                                    currentLogs += parsed.data + "\n";
                                    continue;
                                }

                                if (parsed.type === "llm_response") {
                                    currentData += parsed.data;
                                    continue;
                                }

                                if (parsed.type === "tool_selection") {
                                    currentToolSelection += parsed.data + "\n";
                                    continue;
                                }

                                if (parsed.type === "image") {
                                    currentImage += parsed.data + "\n";
                                    continue;
                                }

                                if (parsed.type === "error") {
                                    currentData += `\n\n **Error:** ${parsed.data}`;
                                    continue;
                                }

                            } catch (e) {
                                showErrorToast("Invalid chunk:" + line);
                            }
                        }

                        setMessages(prev => {
                            const lastIndex = prev.length - 1
                            const last = prev[lastIndex]
                            const updated = [...prev]
                            updated[lastIndex] = {
                                ...last,
                                message: {
                                    ...last.message,
                                    data: currentData,
                                    logs: currentLogs,
                                    image: currentImage,
                                    toolSelection: currentToolSelection,
                                },
                            }
                            return updated
                        })
                    }
                }

            } catch (e: any) {
                if (e.name === 'AbortError') {
                    showErrorToast('Stream request aborted');
                    return;
                }
                const errorResponse: Message = {
                    role: "assistant",
                    message: {
                        data: 'Chillax, there seems to be an issue. Please try again later'
                    }
                }
                setMessages(prev => [...prev, errorResponse])
            } finally {
                setIsLoading(false)
                setIsStreaming(false)
                setController(null)
            }
        }
    }

    const fetchConversations = async (conversationId: string) => {
        try {
            const response = await chatApi.getUpgradeChatHistory(conversationId)
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const formattedMessages: Message[] = response.data.messages.map((item: any) => {
                return {
                    role: item.role,
                    message: {
                        data: item.content,
                        metadata: item.metadata
                    }
                }
            })
            setMessages(formattedMessages)
        } catch (e) {
            console.log(e)
        }
    }
    const getChatTitle = async (conversationId: string) => {
        try {
            const response = await chatApi.generateUpgradeChatTitle(conversationId)
            setChatTitle(response.data.title)
        } catch (e) {
            console.log(e)
        }
    }
    const enhancePrompt = async (prompt: string) => {
        if (!prompt) return;
        setIsEnhancingPrompt(true);
        try {
            const response = await chatApi.enhancePrompt(prompt);
            setInputText(response.data.data);
        } catch (error) {
            showErrorToast('Failed to enhance prompt');
        } finally {
            setIsEnhancingPrompt(false);
        }
    };

    return (
        <ChatContext.Provider
            value={{
                inputText,
                setInputText,
                firstText,
                setFirstText,
                isLoading,
                setIsLoading,
                isStreaming,
                setIsStreaming,
                internetSearchEnabled,
                setInternetSearchEnabled,
                assignmentMode,
                setAssignmentMode,
                browserMode,
                setBrowserMode,
                isEnhancingPrompt,
                enhancePrompt,
                stopResponse,
                messages,
                setMessages,
                handleNewMessage,
                resetChat,
                fetchConversations,
                getChatTitle,
                chatTitle,
                activeStatus,
                setActiveStatus
            }}
        >
            {children}
        </ChatContext.Provider>
    )
}

export const useUpgradeChat = (): ChatContextType => {
    const context = useContext(ChatContext)
    if (!context) throw new Error('useChat must be used within ChatProvider')
    return context
}
