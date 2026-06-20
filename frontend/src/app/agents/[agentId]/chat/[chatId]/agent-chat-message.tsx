import React, { useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { IAgentMessage } from './types'
import axios from 'axios'
import Image from 'next/image'
import { Bot, ChevronDown, ChevronUp, Terminal, User } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { GoDotFill } from 'react-icons/go'

const AgentChatMessage = ({ msg, isThinking }: { msg: IAgentMessage, isThinking?: boolean }) => {
    const [imageUrl, setImageUrl] = React.useState<string | null>(null);
    const [isLogsVisible, setIsLogsVisible] = React.useState<boolean>(true);
    const isUser = msg.role === "user"

    useEffect(() => {
        const getImageUrl = async (image: string) => {
            if (!image) return null;
            let imagePath = image;
            if (image.endsWith('\n')) {
                console.log("Image path ends with /, removing it")
                imagePath = image.slice(0, -1);
            } else {
                imagePath = image;
            }
                        const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || "";
                        const finalUrl = baseUrl ? `${baseUrl.replace(/\/$/, '')}/${imagePath.replace(/^\//, '')}` : `/${imagePath.replace(/^\//, '')}`;
                        setImageUrl(finalUrl);
        }
        if (!msg.message.image) return;
        getImageUrl(msg.message.image)
    }, [msg.message.image])

    return (
        <div className={`flex w-full ${isUser ? "justify-end" : "justify-start"} mb-6`}>
            <div className={`flex max-w-[85%] ${isUser ? "flex-row-reverse" : "flex-row"} gap-3`}>
                {/* Avatar */}
                <div
                    className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${isUser
                        ? " dark:text-white text-black"
                        : " dark:text-white text-black"
                        }`}
                >
                    {isUser ? <User size={16} /> : <Bot size={16} />}
                </div>

                {/* Message Content */}
                <div className="flex flex-col gap-2 min-w-0">
                    {isThinking && (
                        <div className="flex items-center gap-2 text-muted-foreground animate-pulse mt-1">
                            <GoDotFill className="text-orange-600 text-xl" />
                            <span className="text-sm font-medium">Agent is thinking...</span>
                        </div>
                    )}

                    {!isUser && (msg.message.logs || msg.message.toolSelection) && (
                        <Collapsible open={isLogsVisible} onOpenChange={setIsLogsVisible}>
                            <CollapsibleTrigger asChild>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="w-fit h-8 px-3 text-xs text-muted-foreground hover:text-foreground transition-colors dark:text-gray-400 dark:hover:text-gray-200"
                                >
                                    <Terminal size={12} className="mr-1.5" />
                                    View Logs
                                    {isLogsVisible ? (
                                        <ChevronUp size={12} className="ml-1.5" />
                                    ) : (
                                        <ChevronDown size={12} className="ml-1.5" />
                                    )}
                                </Button>
                            </CollapsibleTrigger>

                            <CollapsibleContent className="space-y-2 mt-2">
                                {/* Tool Selection */}
                                {msg.message.toolSelection && (
                                    <Card className="bg-slate-50 dark:bg-slate-950/50 border-slate-200 dark:border-slate-800 transition-colors duration-200">
                                        <CardContent className="p-3">
                                            <div className="flex items-center gap-2 mb-2">
                                                <Terminal size={14} className="text-slate-600 dark:text-slate-400" />
                                                <Badge
                                                    variant="secondary"
                                                    className="text-xs bg-slate-100 dark:bg-slate-900 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700"
                                                >
                                                    Tools Selection
                                                </Badge>
                                            </div>
                                            <pre className="text-xs font-mono text-slate-700 dark:text-slate-300 whitespace-pre-wrap break-words overflow-x-auto max-h-64 overflow-y-auto">
                                                <ReactMarkdown
                                                    components={{
                                                        p: ({ children }) => (
                                                            <p className="text-xs font-mono leading-relaxed mb-1 last:mb-0">{children}</p>
                                                        ),
                                                        a: ({ node, children, ...props }) => (
                                                            <a
                                                                {...props}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                className="text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 underline transition-colors"
                                                            >
                                                                {children}
                                                            </a>
                                                        ),
                                                    }}
                                                >
                                                    {msg.message.toolSelection}
                                                </ReactMarkdown>
                                            </pre>
                                        </CardContent>
                                    </Card>
                                )}

                                {/* System Logs */}
                                {msg.message.logs && (
                                    <Card className="bg-slate-50 dark:bg-slate-950/50 border-slate-200 dark:border-slate-800 transition-colors duration-200">
                                        <CardContent className="p-3">
                                            <div className="flex items-center gap-2 mb-2">
                                                <Terminal size={14} className="text-slate-600 dark:text-slate-400" />
                                                <Badge
                                                    variant="secondary"
                                                    className="text-xs bg-slate-100 dark:bg-slate-900 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700"
                                                >
                                                    System Logs
                                                </Badge>
                                            </div>
                                            <pre className="text-xs font-mono text-slate-700 dark:text-slate-300 whitespace-pre-wrap break-words overflow-x-auto max-h-64 overflow-y-auto">
                                                <ReactMarkdown
                                                    components={{
                                                        p: ({ children }) => (
                                                            <p className="text-xs font-mono leading-relaxed mb-1 last:mb-0">{children}</p>
                                                        ),
                                                        a: ({ node, children, ...props }) => (
                                                            <a
                                                                {...props}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                className="text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 underline transition-colors"
                                                            >
                                                                {children}
                                                            </a>
                                                        ),
                                                    }}
                                                >
                                                    {msg.message.logs}
                                                </ReactMarkdown>
                                            </pre>
                                        </CardContent>
                                    </Card>
                                )}
                            </CollapsibleContent>
                        </Collapsible>
                    )}

                    {msg.message.data && msg.message.data.length > 0 &&
                        <Card
                            className={`${isUser
                                ? " text-white"
                                : "bg-card border-border"
                                } shadow-sm transition-colors duration-200 text-black dark:text-white`}
                        >
                            <CardContent className="p-4">
                                {/* Image */}
                                {imageUrl && imageUrl !== "" && (
                                    <div className="mb-3">
                                        <Image
                                            src={imageUrl || "/placeholder.svg"}
                                            alt="Message attachment"
                                            width={500}
                                            height={300}
                                            className="rounded-lg max-w-full h-auto border border-border/20 dark:border-gray-600/20"
                                        />
                                    </div>
                                )}

                                {/* Message Text */}
                                {msg.message.data && (
                                    <div className="prose prose-sm max-w-none dark:prose-invert break-words">
                                        <ReactMarkdown
                                            components={{
                                                a: ({ node, children, ...props }) => (
                                                    <a
                                                        {...props}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className={`${isUser
                                                            ? "text-blue-100 hover:text-white underline"
                                                            : "text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 underline"
                                                            } transition-colors text-sm`}
                                                    >
                                                        {children}
                                                    </a>
                                                ),
                                                p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed text-sm whitespace-pre-wrap">{children}</p>,
                                                ul: ({ children }) => <ul className="list-disc pl-5 mb-2 space-y-1 text-sm">{children}</ul>,
                                                ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 space-y-1 text-sm">{children}</ol>,
                                                li: ({ children }) => <li className="leading-relaxed text-sm">{children}</li>,
                                                code: ({ children }) => (
                                                    <code
                                                        className={`px-1.5 py-0.5 rounded text-sm font-mono ${isUser
                                                            ? "bg-blue-600/50 text-blue-100"
                                                            : "bg-muted text-muted-foreground dark:bg-gray-700 dark:text-gray-300"
                                                            }`}
                                                    >
                                                        {children}
                                                    </code>
                                                ),
                                                img: ({ src, alt }) => (
                                                    <img 
                                                        src={src} 
                                                        alt={alt} 
                                                        className="rounded-lg max-w-full h-auto border border-border/20 dark:border-gray-600/20 my-2 shadow-sm"
                                                    />
                                                ),
                                            }}
                                        >
                                            {msg.message.data}
                                        </ReactMarkdown>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    }
                </div>
            </div>
        </div>
    )
}

export default AgentChatMessage