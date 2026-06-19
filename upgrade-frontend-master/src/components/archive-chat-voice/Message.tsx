// "use client";

// import { ChatMessage, MessageProps } from "../types/chat";
// import { useRef, useEffect, useState } from "react";

// const Message: React.FC<MessageProps> = ({ message, isLatest }) => {
//   const messageRef = useRef<HTMLDivElement>(null);

//   useEffect(() => {
//     if (isLatest && messageRef.current) {
//       messageRef.current.scrollIntoView({ behavior: "smooth" });
//     }
//   }, [isLatest, message.content.text]);

//   return (
//     <div
//       ref={messageRef}
//       className={`message ${
//         message.role === "assistant" ? "assistant" : "user"
//       }`}
//     >
//       <div className="message-content">
//         {message.content.imageUrl ? (
//           <img
//             src={message.content.imageUrl}
//             alt="Generated content"
//             className="max-w-full h-auto"
//           />
//         ) : (
//           <div className="text-content">
//             {message.content.text}
//             {isLatest &&
//               message.role === "assistant" &&
//               !message.content.text && <span className="cursor">▋</span>}
//           </div>
//         )}
//       </div>
//     </div>
//   );
// };

// // Main chat component example
// const ChatInterface: React.FC = () => {
//   const [messages, setMessages] = useState<ChatMessage[]>([]);
//   const [inputText, setInputText] = useState("");
//   const [loading, setLoading] = useState(false);
//   const [internetSearchEnabled, setInternetSearchEnabled] = useState(false);

//   // Your handleNewMessage function here...

//   return (
//     <div className="chat-container">
//       <div className="messages-container">
//         {messages.map((message, index) => (
//           <Message
//             key={index}
//             message={message}
//             isLatest={index === messages.length - 1}
//           />
//         ))}
//       </div>

//       <div className="input-container">
//         <input
//           type="text"
//           value={inputText}
//           onChange={(e) => setInputText(e.target.value)}
//           disabled={loading}
//           placeholder="Type your message..."
//           className="chat-input"
//         />
//         <button
//           onClick={() => handleNewMessage("user", inputText)}
//           disabled={loading || !inputText.trim()}
//           className="send-button"
//         >
//           Send
//         </button>
//       </div>
//     </div>
//   );
// };

// export default ChatInterface;
