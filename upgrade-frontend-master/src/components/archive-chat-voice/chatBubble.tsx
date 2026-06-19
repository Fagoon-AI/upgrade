// components/chat/ChatBubble.tsx
import React from "react";

interface ChatBubbleProps {
  text: string;
  isUser: boolean;
}

export const ChatBubble = ({ text, isUser }: ChatBubbleProps) => (
  <div
    className={`p-3 m-2 rounded-lg ${
      isUser
        ? "bg-blue-500 text-white self-end"
        : "bg-gray-300 text-black self-start"
    }`}
  >
    {text}
  </div>
);
