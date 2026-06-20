"use client";

import React, { useState, useEffect, useRef, Suspense } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import axios from '@/lib/api/axios';
import { useSearchParams } from "next/navigation";
import { X, Send, Trash2, Download, Copy, Bot, Zap, Menu } from "lucide-react";
import { showSuccessToast, showErrorToast } from "@/utils/toast";
// Remove these lines
// import { Button } from "@/components/ui/button"
// import { Input } from "@/components/ui/input"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface Agent {
  agent_id: string;
  agent_name: string;
  agent_description?: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

const AgentChat: React.FC = () => (
  <Suspense fallback={<LoadingState />}>
    <AgentChatContent />
  </Suspense>
);

const LoadingState: React.FC = () => (
  <div className="h-screen flex items-center justify-center bg-gradient-to-br from-purple-50 to-indigo-50 dark:from-gray-900 dark:to-gray-800">
    <div className="text-center">
      <Bot className="w-16 h-16 mx-auto text-purple-500 animate-pulse" />
      <p className="mt-4 text-gray-600 dark:text-gray-300">
        Preparing your AI assistant...
      </p>
    </div>
  </div>
);

const MessageBubble: React.FC<{
  message: ChatMessage;
  onCopy: () => void;
}> = ({ message, onCopy }) => (
  <div
    className={`flex ${message.role === "user" ? "justify-end" : "justify-start"
      } mb-4 relative group`}
  >
    <div
      className={`
        ${message.role === "user"
          ? "bg-purple-100 dark:bg-purple-900"
          : "bg-gray-100 dark:bg-gray-700"
        } 
        p-4 rounded-xl max-w-[85%] shadow-sm
      `}
    >
      {message.role === "assistant" && (
        <div className="absolute -left-8 top-2">
          <Bot className="w-6 h-6 text-purple-500" />
        </div>
      )}
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        className="prose dark:prose-invert max-w-none"
      >
        {message.content}
      </ReactMarkdown>
      <div className="text-xs text-gray-500 dark:text-gray-400 mt-2 flex items-center justify-between">
        <span>{new Date(message.timestamp).toLocaleTimeString()}</span>
        <Button
          variant="outline"
          size="icon"
          onClick={onCopy}
          className="opacity-0 group-hover:opacity-100 transition-opacity"
          title="Copy message"
        >
          <Copy className="w-4 h-4" />
        </Button>
      </div>
    </div>
  </div>
);

const AgentChatContent: React.FC = () => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [userInput, setUserInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const searchParams = useSearchParams();
  const agentQuery = searchParams.get("agent");


  useEffect(() => {
    if (agents.length > 0 && !selectedAgent && agentQuery) {
      const matchedAgent = agents.find(
        (a) => a.agent_name.toLowerCase() === agentQuery.toLowerCase()
      );
      setSelectedAgent(matchedAgent || agents[0]);
    }
  }, [agents, agentQuery]);

  const user_id =
    typeof window !== "undefined"
      ? JSON.parse(
        localStorage.getItem("user") || '{"_id":"66ac99b7a2f0a35b8b149299"}'
      )._id
      : "66ac99b7a2f0a35b8b149299";

  useEffect(() => {
    fetchAgents();
  }, []);


  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const fetchAgents = async () => {
    try {
      const response = await axios.post("/api/v1/agents", { user_id });
      setAgents(response.data);
    } catch (error) {
      showErrorToast("Failed to load AI assistants");
    }
  };

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      showSuccessToast("Copied to clipboard");
    } catch (err) {
      showErrorToast("Failed to copy");
    }
  };

  const downloadChat = () => {
    const chatContent = messages
      .map(
        (msg) =>
          `${msg.role.toUpperCase()} (${new Date(
            msg.timestamp
          ).toLocaleString()})\n${msg.content}\n\n`
      )
      .join("");
    const blob = new Blob([chatContent], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `chat-${new Date().toISOString()}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const sendMessage = async () => {
    if (!userInput.trim() || !selectedAgent) return;

    const newMessage: ChatMessage = {
      role: "user",
      content: userInput,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, newMessage]);
    setIsLoading(true);
    setUserInput("");

    try {
      const messagesAPI = [...messages, newMessage].map((msg) => ({
        role: msg.role,
        content: msg.content,
      }));

      const response = await axios.post(
        "/api/v1/upgrade/chat",
        {
          convo: messagesAPI,
          agent: true,
          agent_id: selectedAgent.agent_id,
        }
      );

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response.data.response || response.data,
          timestamp: Date.now(),
        },
      ]);
    } catch (error) {
      showErrorToast("Failed to send message");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen max-w-6xl mx-auto bg-white dark:bg-gray-900 shadow-xl">
      {/* Header */}
      <header className="border-b dark:border-gray-700 p-4 flex items-center justify-between sticky top-0 bg-white dark:bg-gray-900 z-10">
        <div className="flex items-center space-x-4">
          <Zap className="w-8 h-8 text-purple-500" />
          <div>
            <h1 className="font-bold text-lg dark:text-white">
              {selectedAgent?.agent_name || "AI Assistant"}
            </h1>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {selectedAgent?.agent_description || "Ready to help you"}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          {/* <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="icon">
                <Menu className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {agents.map((agent) => (
                <DropdownMenuItem
                  key={agent.agent_id}
                  onClick={() => setSelectedAgent(agent)}
                >
                  {agent.agent_name}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu> */}
          {messages.length > 0 && (
            <>
              <Button
                variant="outline"
                size="icon"
                onClick={downloadChat}
                title="Download chat"
              >
                <Download className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                onClick={() => setMessages([])}
                title="Clear chat"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </>
          )}
        </div>
      </header>

      {/* Chat Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 bg-gray-50 dark:bg-gray-800">
        <div className="space-y-4 max-w-3xl mx-auto">
          {messages.map((message, index) => (
            <MessageBubble
              key={index}
              message={message}
              onCopy={() => copyToClipboard(message.content)}
            />
          ))}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-gray-100 dark:bg-gray-700 p-4 rounded-xl">
                <div className="animate-pulse flex space-x-4">
                  <div className="flex-1 space-y-4">
                    <div className="h-4 bg-gray-300 dark:bg-gray-600 rounded w-3/4"></div>
                    <div className="h-4 bg-gray-300 dark:bg-gray-600 rounded w-1/2"></div>
                  </div>
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>
      </div>

      {/* Message Input */}
      <div className="border-t dark:border-gray-700 p-4 bg-white dark:bg-gray-900 sticky bottom-0">
        <div className="flex items-center space-x-2 max-w-3xl mx-auto">
          <Input
            type="text"
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            placeholder="Type your message..."
            disabled={isLoading}
            className="flex-1"
          />
          <Button
            onClick={sendMessage}
            disabled={isLoading || !userInput.trim()}
          >
            <Send className="w-5 h-5" />
          </Button>
        </div>
      </div>
    </div>
  );
};

const Button: React.FC<
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: "default" | "outline";
    size?: "default" | "icon";
  }
> = ({
  children,
  variant = "default",
  size = "default",
  className = "",
  ...props
}) => {
    const baseClasses =
      "font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 transition";
    const variantClasses =
      variant === "outline"
        ? "border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800"
        : "bg-purple-600 text-white hover:bg-purple-700";
    const sizeClasses = size === "icon" ? "p-2" : "px-4 py-2";

    return (
      <button
        className={`${baseClasses} ${variantClasses} ${sizeClasses} ${className}`}
        {...props}
      >
        {children}
      </button>
    );
  };

const Input: React.FC<React.InputHTMLAttributes<HTMLInputElement>> = ({
  className = "",
  ...props
}) => {
  return (
    <input
      className={`w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-800 dark:text-white ${className}`}
      {...props}
    />
  );
};

export default AgentChat;
