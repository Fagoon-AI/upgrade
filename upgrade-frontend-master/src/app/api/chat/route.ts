import { API_BASE_URL } from "@/utils/api/api";
import { logger } from "@/utils/data/logger";
import { StreamError, ApiError } from "@/utils/data/errors";
import axios from 'axios';
import { NextRequest, NextResponse } from "next/server";
import { baseAPIdomain } from "@/components/BaseDomain";

const CHAT_API_ENDPOINT = `${baseAPIdomain}/api/upgrade/chat/stream`;
const DEFAULT_MODEL = "gpt-3.5-turbo-0125";

// Model mapping configuration
// const MODEL_MAPPING: Record<string, string> = {
//   "fagoon-nova": "gpt-3.5-turbo-0125",
//   "llama3-8b-8192": "llama3-8b-8192",
//   "deepseek-dist-llama-70b": "deepseek-r1-distill-llama-70b",
//   "gpt-3.5-turbo": "gpt-3.5-turbo-0125",
//   "llama3.1-8b-instruct": "meta-llama/Llama-3.1-8B-Instruct",
//   "deepseek-coder-1.3b": "deepseek-ai/deepseek-coder-1.3b-instruct",
//   "deepseek-R1-Dist-Qwen-32B": "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
//   "falcon-7b": "tiiuae/falcon-7b-instruct",
//   "llama-3.1-70b-inst": "meta-llama/Llama-3.1-70B-Instruct",
//   "Nous-Hermes-2-Mixtral": "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO",
//   "starchat2-15b": "HuggingFaceH4/starchat2-15b-v0.1",
//   "codellama-34b": "codellama/CodeLlama-34b-Instruct-hf",
//   "gemini-1.5-flash": "gemini-1.5-flash",
//   "gemini-2.0-flash": "gemini-2.0-flash",
// };

class ContentProcessor {
  private static codeBlockRegex = /(`{1,3})(?:[\s\S]*?)(?:\1)/g;
  private static placeholderPrefix = "__CODE_BLOCK_";
  private static placeholderSuffix = "__";

  static processContent(rawContent: string): string {
    const { text, blocks } = this.preserveCodeBlocks(rawContent);
    return this.restoreCodeBlocks(this.unescapeContent(text), blocks);
  }

  private static unescapeContent(text: string): string {
    const unescapeMap: Record<string, string> = {
      "\\n": "\n",
      "\\t": "\t",
      '\\"': '"',
      "\\'": "'",
      "\\\\": "\\",
      "\\`": "`",
    };

    return text.replace(
      /\\[ntr'"`\\]/g,
      (match) => unescapeMap[match] || match
    );
  }

  private static preserveCodeBlocks(content: string): {
    text: string;
    blocks: string[];
  } {
    const blocks: string[] = [];
    const processed = content.replace(this.codeBlockRegex, (match) => {
      blocks.push(match);
      return `${this.placeholderPrefix}${blocks.length - 1}${
        this.placeholderSuffix
      }`;
    });
    return { text: processed, blocks };
  }

  private static restoreCodeBlocks(text: string, blocks: string[]): string {
    return blocks.reduce(
      (acc, block, index) =>
        acc.replace(
          new RegExp(
            `${this.placeholderPrefix}${index}${this.placeholderSuffix}`,
            "g"
          ),
          () => block
        ),
      text
    );
  }
}

class StreamHandler {
  private decoder = new TextDecoder();
  private buffer = "";
  private fullContent = "";
  private lastChunk = "";
  private usageChunk = "";
  private static readonly CHUNK_DELIMITER = "ChatCompletionChunk";
  private static readonly TOKEN_USAGE_PATTERNS = [
    /CompletionUsage\(.*?total_tokens=(\d+)/,
    /total_tokens=(\d+)/,
    /"total_tokens":\s*(\d+)/,
    /"usage":\s*{\s*"total_tokens":\s*(\d+)/,
  ];

  public getFullContent(): string {
    return this.fullContent;
  }

  public getUsageChunk(): string {
    return this.usageChunk;
  }

  public getLastChunk(): string {
    return this.lastChunk;
  }

  private extractContent(chunk: string): string | null {
    try {
      const contentMatch = chunk.match(/content=(['"])((?:\\.|.)*?)\1/);
      return contentMatch?.[2] || null;
    } catch (error) {
      logger.error("Content extraction failed", { error, chunk });
      return null;
    }
  }

  public static calculateTokenUsage(
    content: string,
    usageChunk: string
  ): number {
    try {
      // First, try to extract from usage chunk
      for (const pattern of StreamHandler.TOKEN_USAGE_PATTERNS) {
        const match = usageChunk.match(pattern);
        if (match && match[1]) {
          return parseInt(match[1], 10);
        }
      }

      // Fallback: estimate based on word count
      const wordCount = content.split(/\s+/).length;
      return Math.max(100, Math.ceil(wordCount * 1.3)); // Minimum 100 tokens
    } catch (error) {
      logger.error("Token calculation failed", { error });
      return 100; // Safe default
    }
  }

  public async processStream(
    controller: ReadableStreamDefaultController,
    response: Response
  ): Promise<void> {
    const reader = response.body?.getReader();
    if (!reader) throw new StreamError("No response body");

    try {
      await this.processChunks(reader, controller);
    } finally {
      reader.releaseLock();
    }
  }

  private async processChunks(
    reader: ReadableStreamDefaultReader<Uint8Array>,
    controller: ReadableStreamDefaultController
  ): Promise<void> {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      this.buffer += this.decoder.decode(value, { stream: true });
      const chunks = this.buffer.split(StreamHandler.CHUNK_DELIMITER);
      this.buffer = chunks.pop() || "";

      // Store the last chunk with token usage info
      for (let i = chunks.length - 1; i >= 0; i--) {
        const chunk = chunks[i];
        if (
          chunk &&
          (chunk.includes("CompletionUsage") ||
            chunk.includes("total_tokens") ||
            chunk.includes("usage="))
        ) {
          this.usageChunk = chunk;
          break;
        }
      }

      this.lastChunk = chunks[chunks.length - 1] || "";
      await this.processChunkArray(chunks, controller);
    }

    // Process any remaining content in buffer
    await this.processRemainingBuffer(controller);
  }

  private async processChunkArray(
    chunks: string[],
    controller: ReadableStreamDefaultController
  ): Promise<void> {
    for (const chunk of chunks) {
      const rawContent = this.extractContent(chunk);
      if (!rawContent) continue;

      const processedContent = ContentProcessor.processContent(rawContent);
      if (processedContent) {
        await this.enqueueContent(controller, processedContent);
      }
    }
  }

  private async processRemainingBuffer(
    controller: ReadableStreamDefaultController
  ): Promise<void> {
    if (this.buffer) {
      const rawContent = this.extractContent(this.buffer);
      if (rawContent) {
        const processedContent = ContentProcessor.processContent(rawContent);
        await this.enqueueContent(controller, processedContent);
      }
    }
  }

  private async enqueueContent(
    controller: ReadableStreamDefaultController,
    content: string
  ): Promise<void> {
    controller.enqueue(`data: ${JSON.stringify({ content })}\n\n`);
    this.fullContent += content;
  }
}

async function updateChatHistory(
  chatHistoryId: string,
  content: string,
  tokenUsage: number,
  model: string,
  token: string,
  data: string| null
): Promise<void> {
  try {

    const userStr = localStorage.getItem("user");
    const user = userStr ? JSON.parse(userStr) as { _id: string } : null;
    const user_id = user?._id || null;
    await axios.post(
      `${API_BASE_URL}/api/v1/chat/create/chat`,
      {
        role: "assistant",
        message: content,
        internet_search: false,
        uuid: chatHistoryId,
        model,
        data,
        tokenUsage,
        user_id
      },
      { headers: { Authorization: `Bearer ${token}` } }
    );
  } catch (error) {
    logger.error("Failed to update chat history", { error, chatHistoryId });
    throw new ApiError("Failed to update chat history", 500);
  }
}

async function validateToken(token: string): Promise<boolean> {
  try {
    const response = await axios.get(`${API_BASE_URL}/api/v1/chat/checkToken`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (response.data.status === "error") {
      return false;
    }

    const tokenAvailable = response.data.token.token;
    return tokenAvailable > 0;
  } catch (error) {
    logger.error("Token validation failed", { error });
    return false;
  }
}

export async function POST(request: NextRequest) {
  try {
    const { internet_search, convo, chatHistoryId, token, selected_model,data } =
      await request.json();

    // Token validation
    if (token) {
      // const isTokenValid = await validateToken(token);
      const isTokenValid = true;
      if (!isTokenValid) {
        return NextResponse.json(
          {
            error: "Token Error",
            details: "Invalid token or insufficient token balance",
          },
          { status: 401 }
        );
      }
    }

    // Map frontend model to backend model
    const model = selected_model;

    logger.info("Chat request initiated", {
      internetSearch: internet_search ?? false,
      model,
      hasHistory: !!chatHistoryId,
    });

    const streamHandler = new StreamHandler();

    const stream = new ReadableStream({
      async start(controller) {
        try {
          const response = await fetch(CHAT_API_ENDPOINT, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Accept: "text/event-stream",
            },
            body: JSON.stringify({
              internet_search: internet_search ?? false,
              convo,
              converstion_id: chatHistoryId,
              selected_model: model,
            }),
          });

          if (!response.ok) {
            throw new ApiError(
              `API request failed: ${response.statusText}`,
              response.status
            );
          }

          await streamHandler.processStream(controller, response);

          // Calculate token usage from usage chunk or content
          const finalContent = streamHandler.getFullContent();
          const usageChunk = streamHandler.getUsageChunk();
          const tokenUsage = StreamHandler.calculateTokenUsage(
            finalContent,
            usageChunk
          );

          logger.info("Stream processing completed", {
            contentLength: finalContent.length,
            tokenUsage,
          });

          // Update chat history if chatHistoryId is provided
          if (chatHistoryId && token) {
            await updateChatHistory(
              chatHistoryId,
              finalContent,
              tokenUsage,
              model,
              data,
              token
            );
          }

          controller.close();
        } catch (error) {
          logger.error("Stream processing failed", { error });
          controller.error(
            error instanceof Error
              ? error
              : new StreamError("Stream processing failed")
          );
        }
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch (error) {
    logger.error("Request processing failed", { error });
    return NextResponse.json(
      {
        error: "Failed to process request",
        details: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 }
    );
  }
}
