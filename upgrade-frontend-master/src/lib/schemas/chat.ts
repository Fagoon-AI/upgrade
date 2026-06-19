import { z } from 'zod';

export const chatMessageSchema = z.object({
  role: z.enum(['user', 'assistant']),
  message: z.string(),
  uuid: z.union([z.string(), z.array(z.string())]),
  selected_model: z.string().optional(),
  conversation_id: z.union([z.string(), z.array(z.string())]),
  user_id: z.string().nullable(),
  data: z.string().nullable().optional(),
  internet_search: z.boolean().optional(),
  tokenUsage: z.number().optional(),
  isAssignmentMode: z.boolean().optional(),
});

export type ChatMessagePayload = z.infer<typeof chatMessageSchema>;

export const chatInputSchema = z.object({
  message: z
    .string()
    .min(1, "Message cannot be empty")
    .max(4000, "Message too long"),

  fileUrl: z.string().optional().nullable(),
});

export type ChatInputForm = z.infer<typeof chatInputSchema>;