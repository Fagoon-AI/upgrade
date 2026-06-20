import { FragmentSchema } from './schema'
import { ExecutionResult } from './types'
import { DeepPartial } from 'ai'

export type MessageText = {
  type: 'text'
  text: string
}

export type MessageCode = {
  type: 'code'
  text: string
}

export type MessageImage = {
  type: 'image'
  image: string
}

export type VibeCoderMessage = {
  role: 'assistant' | 'user'
  content: Array<MessageText | MessageCode | MessageImage>
  object?: DeepPartial<FragmentSchema>
  result?: ExecutionResult
}

export type Message = {
  role: 'assistant' | 'user'
  message: {
    logs?: string,
    toolSelection?: string,
    image?: string,
    data: string,
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
}

export function toAISDKMessages(messages: VibeCoderMessage[]) {
  return messages.map((message) => ({
    role: message.role,
    content: message.content.map((content) => {
      if (content.type === 'code') {
        return {
          type: 'text',
          text: content.text,
        }
      }

      return content
    }),
  }))
}

export async function toMessageImage(files: File[]) {
  if (files.length === 0) {
    return []
  }

  return Promise.all(
    files.map(async (file) => {
      const base64 = Buffer.from(await file.arrayBuffer()).toString('base64')
      return `data:${file.type};base64,${base64}`
    }),
  )
}
