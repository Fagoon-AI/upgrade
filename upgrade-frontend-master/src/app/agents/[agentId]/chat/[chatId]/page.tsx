"use client"

import type React from "react"
import { useEffect, useState, useRef } from "react"
import { Button } from "@/components/ui/button"
import { ChevronLeft, Loader2, ArrowDown } from "lucide-react"
import { useParams } from "next/navigation"
import axios from '@/lib/api/axios'
import { API_ENDPOINTS } from "@/utils/api/api"
import AgentChatInput from "./agent-chat-input"
import { IAgentMessage, IAgentResponseType } from "./types"
import AgentChatMessage from "./agent-chat-message"
import { GoDotFill } from "react-icons/go"
import { useSearchParams } from "next/navigation"
import { useQueryClient, useQuery } from "@tanstack/react-query"
import { IAgentView } from "@/types/agent"


export default function Component() {
    const params = useParams();
    const queryClient = useQueryClient();
    const [messages, setMessages] = useState<IAgentMessage[]>([])
    const [chatName, setChatName] = useState("AI Agent")
    const [loading, setLoading] = useState(false)
    const [isFetchingHistory, setIsFetchingHistory] = useState(true)
    const messagesEndRef = useRef<HTMLDivElement>(null)
    const scrollContainerRef = useRef<HTMLDivElement>(null)
    const [showScrollButton, setShowScrollButton] = useState(false)
    const searchParams = useSearchParams()

    // Get userId: prefer URL param, then cached agents list, then fetch agent details
    const searchParamUserId = searchParams.get('userId')
    const cachedAgents = queryClient.getQueryData<IAgentView[]>(['agents', 'all'])
    const agentFromCache = cachedAgents?.find(
        (a: any) => a.id === params.agentId || a._id === params.agentId
    )
    const cachedUserId = searchParamUserId || (agentFromCache as any)?.user_id

    // Fallback: fetch agent details to get user_id if not available from cache/URL
    const { data: agentDetails } = useQuery({
        queryKey: ['agent-details', params.agentId],
        queryFn: async () => {
            const response = await axios.get(`${API_ENDPOINTS.AGENT}/agent`)
            const agents = response.data?.data?.agents || response.data?.agents || []
            return agents.find((a: any) => a.id === params.agentId || a._id === params.agentId)
        },
        enabled: !cachedUserId, // only fetch if we don't already have the userId
        staleTime: 1000 * 60 * 10,
    })

    const userId = cachedUserId || agentDetails?.user_id;

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
    }

    const handleScroll = () => {
        if (!scrollContainerRef.current) return;
        const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
        if (scrollHeight - scrollTop - clientHeight > 150) {
            setShowScrollButton(true);
        } else {
            setShowScrollButton(false);
        }
    }

    useEffect(() => {
        if (!showScrollButton) {
            scrollToBottom();
        }
    }, [messages])

    useEffect(() => {
        const getChatHistroy = async () => {
            setIsFetchingHistory(true);
            try {
                const response = await axios.get(`${API_ENDPOINTS.AGENT}/agent/chat/${params.chatId}`)
                const chats = response.data.data.chat || response.data.data.history || []
                setChatName(response.data.data.title || "AI Agent")
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                setMessages(chats.map((chat: any) => {
                    const metadata = Array.isArray(chat?.metadata) ? chat.metadata : []
                    const toolSelectionEntry = metadata?.find((item: { type: string, data: string }) => item.type === "tool_selection")
                    let finalLogs = ""
                    metadata?.find((item: { type: string, data: string }) => item.type === "status")?.data.map((item: string) => finalLogs += item + "\n")
                    return {
                        role: chat.role,
                        message: {
                            data: chat.message || chat.content || "",
                            logs: finalLogs,
                            image: chat?.images?.image || "",
                            toolSelection: toolSelectionEntry?.data || "",
                        }
                    }
                }))
            } catch (error) {
                console.error("Failed to load chat history:", error)
            } finally {
                setIsFetchingHistory(false);
            }
        }
        getChatHistroy()
    }, [params])
    const handleNewMessage = async (message: string) => {
        const isFirstMessage = messages.length === 0;
        setLoading(true)
        if (!userId) return console.error("User not found")
        const tempMessage: IAgentMessage = {
            role: "assistant",
            message: {
                data: "",
            }
        }

        setMessages(prev => [...prev, tempMessage])
        try {
            const response = await fetch(`${API_ENDPOINTS.AGENT}/agent/chat/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    conversation_id: params.chatId,
                    message,
                    agent_id: params.agentId,
                    user_id: userId,
                }),
                credentials: 'include'
            })

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
                    const lines = chunkText.split('\n')
                    for (let i = 0; i < lines.length; i++) {
                        const line = lines[i];
                        if (!line.trim()) continue; // Skip empty lines between SSE events

                        console.log("Received chunk:", line)
                        let payload = line;
                        if (payload.startsWith('data: ')) {
                            payload = payload.substring(6);
                        } else if (payload.startsWith('data:')) {
                            payload = payload.substring(5);
                        }

                        try {
                            const parsed = JSON.parse(payload) as {
                                type: IAgentResponseType
                                data: string
                            }
                            if (parsed && parsed.type) {
                                if (parsed.type === 'status') {
                                    currentLogs += parsed.data + "\n"
                                    continue
                                }
                                if (parsed.type === 'llm_response') {
                                    currentData += parsed.data
                                    continue
                                }
                                if (parsed.type === 'tool_selection') {
                                    currentToolSelection += parsed.data + "\n"
                                    continue
                                }
                                if (parsed.type === 'image') {
                                    currentImage += parsed.data + "\n"
                                    continue
                                }
                                if (parsed.type === 'error') {
                                    currentData += `\n\n❌ **Error:** ${parsed.data}`
                                    continue
                                }
                            } else {
                                currentData += payload
                            }
                        } catch (e) {
                            if (payload === "") {
                                currentData += "\n"
                            } else {
                                currentData += payload.replace(/\\n/g, '\n')
                            }
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

            // Generate title if it's the first message
            if (isFirstMessage) {
                try {
                    const titleResponse = await axios.post(`${API_ENDPOINTS.AGENT}/agent/chat/title`, {
                        conversation_id: params.chatId,
                        user_id: userId,
                    })
                    const generatedTitle = titleResponse.data?.data?.data || titleResponse.data?.data || "New Chat";
                    setChatName(generatedTitle);
                    queryClient.invalidateQueries({ queryKey: ["agent-conversations", params.agentId] });
                } catch (e) {
                    console.error("Failed to generate title:", e);
                }
            }

        } catch (e) {
            console.log(e)
            const errorResponse: IAgentMessage = {
                role: "assistant",
                message: {
                    data: "Something went wrong. Please try again later.",
                }
            }
            setMessages(prev => [...prev, errorResponse])
        } finally {
            setLoading(false)
        }
    }


    const handleSubmit = (text: string) => {
        if (text) {
            setMessages([...messages, { role: "user", message: { data: text } }])
            handleNewMessage(text)
        }
    }
    if (!params.agentId || !params.chatId) {
        return <div className="flex items-center justify-center h-screen text-lg text-muted-foreground">Loading...</div>
    }
    return (
        <div className="min-h-screen  flex flex-col">
            {isFetchingHistory ? (
                <div className="flex-1 flex flex-col items-center justify-center p-4 h-full gap-4">
                    <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    <p className="text-muted-foreground font-medium animate-pulse">Fetching previous messages...</p>
                </div>
            ) : messages.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center p-4">
                    <div className="w-full max-w-3xl mx-auto space-y-8">
                        <div className="text-center space-y-4">
                            <h1 className="text-4xl md:text-5xl font-bold text-foreground">Welcome to Agent Chat</h1>
                            <p className="text-lg text-muted-foreground max-w-xl mx-auto">
                                Get started by Script a task and the Agent can do the rest.
                            </p>
                        </div>
                        <AgentChatInput handleSubmit={handleSubmit} agent_id={params.agentId as string} />
                    </div>
                </div>
            ) : (
                <div className="flex-1 flex flex-col overflow-auto max-h-screen">
                    <div className="z-10 backdrop-blur-sm border-b">
                        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center">
                            <Button variant="ghost" size="icon" className="mr-2">
                                <ChevronLeft className="h-5 w-5" />
                                <span className="sr-only">Back</span>
                            </Button>
                            <h1 className="text-lg font-medium text-foreground truncate">{chatName}</h1>
                        </div>
                    </div>

                    {/* Messages */}
                    <div 
                        className="flex-1 overflow-y-auto p-4 relative custom-scrollbar"
                        ref={scrollContainerRef}
                        onScroll={handleScroll}
                    >
                        <div className="max-w-5xl mx-auto space-y-4 pb-20 relative">
                            {messages.map((msg, index) => {
                                const isLastAssistantMessage = loading && 
                                    msg.role === "assistant" && 
                                    index === messages.length - 1 && 
                                    (!msg.message.data || msg.message.data.length === 0);

                                return (
                                    <div key={index}>
                                        <AgentChatMessage msg={msg} isThinking={isLastAssistantMessage} />
                                    </div>
                                );
                            })}
                            <div ref={messagesEndRef} />
                        </div>
                        {showScrollButton && (
                            <Button 
                                variant="secondary" 
                                size="icon" 
                                className="sticky bottom-6 left-1/2 -translate-x-1/2 rounded-full shadow-lg z-50 opacity-90 hover:opacity-100 transition-opacity"
                                onClick={() => {
                                    setShowScrollButton(false);
                                    scrollToBottom();
                                }}
                            >
                                <ArrowDown className="w-5 h-5 text-primary" />
                            </Button>
                        )}
                    </div>
                    <div className="w-full max-w-5xl mx-auto px-4 py-3 border-t sticky bottom-0">
                        <AgentChatInput handleSubmit={handleSubmit} agent_id={params.agentId as string} />
                    </div>
                </div>
            )}
        </div>
    )
}

