export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
  metadata?: {
    data: Array<{
      type: "log" | "generated_image" | "generated_video";
      data: string | {
        url: string;
        db_id: string;
        prompt: string;
        summary: string;
        asset_type: string;
      };
    }>;
  };
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: {
    text: string;
    imageUrl?: string;
    isPdf?: boolean;
    pdfName?: string;
  };
  isAudioPlaying?: boolean;
  isAssignmentMode?: boolean;
  response?: string | null;
  prompt?: string | null;
  isPdf?: boolean;
  pdfName?: string | null;
  isLoading?: boolean;
}

export interface NewsItem {
  source: {
    id: string;
    name: string;
  };
  author: string;
  title: string;
  description: string;
  url: string;
  urlToImage: string;
  publishedAt: string;
  content: string;
}

// Interface for API conversation format
export interface APIMessage {
  role: "user" | "assistant";
  content: string;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  isCustom: boolean;
  agent_id?: string;
  creation_time?: string;
  status?: string;
  capabilities?: string[];
  usageCount?: number;
}

export interface Command {
  id?: string;
  name: string;
  description: string;
  prefix?: string;
  icon?: React.ReactNode;
}

export const commands: Command[] = [
  { name: "/imagen", description: "Generate an image based on your prompt" },
  { name: "/email", description: "Write and format emails" },
  // { name: "/help", description: "Show list of available commands" },
  // { name: "/image-analysis", description: "Analyze images" },
  // { name: "/chat-evaluation", description: "Evaluate chat responses" },
  // { name: "/clear", description: "Clear chat history" },
];

export const FEATURED_AGENTS: Agent[] = [
  {
    id: "business-copilot",
    name: "Business Copilot",
    description:
      "Enterprise-grade AI assistant for business strategy and operations",
    isCustom: false,
    // capabilities: ["Strategy Analysis", "Market Research", "Report Generation"],
    usageCount: 15420,
  },
  {
    id: "creative-studio",
    name: "Creative Studio",
    description:
      "AI-powered creative assistant for content creation and ideation",
    isCustom: false,
    // capabilities: ["Content Writing", "Brainstorming", "Image Prompting"],
    usageCount: 12350,
  },
  {
    id: "data-analyst",
    name: "Data Analyst",
    description: "Advanced data analysis and visualization assistant",
    isCustom: false,
    // capabilities: ["Data Analysis", "Visualization", "Reporting"],
    usageCount: 9840,
  },
];

export type Model = {
  id: string;
  label: string;
  icon: string;
};

export type Conversation = {
  conversation_id: string;
  title: string;
  last_message: string;
  created_at: string;
  updated_at: string;
};

export type ConversationResponse = {
  status: string;
  message: string;
  data: {
    conversations: Conversation[];
    total: number;
    limit: number;
    offset: number;
  };
};