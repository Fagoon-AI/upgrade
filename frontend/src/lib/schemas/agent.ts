import { z } from 'zod';

export const agentProfileSchema = z.object({
  agent_name: z.string().min(3, 'Agent name must be at least 3 characters'),
  description: z.string().min(1, 'Description is required'),
  image: z.string().optional(),
});

export const modelSettingsSchema = z.object({
  llm_model: z.string().min(1, 'Model is required'),
  api_key: z.string().optional(),
  temperature: z.number().min(0).max(1),
  max_tokens: z.preprocess((val) => (val === "" || val === null || isNaN(Number(val)) ? undefined : Number(val)), z.number().optional()),
  top_p: z.preprocess((val) => (val === "" || val === null || isNaN(Number(val)) ? undefined : Number(val)), z.number().optional()),
  frequency_penalty: z.preprocess((val) => (val === "" || val === null || isNaN(Number(val)) ? undefined : Number(val)), z.number().optional()),
  presence_penalty: z.preprocess((val) => (val === "" || val === null || isNaN(Number(val)) ? undefined : Number(val)), z.number().optional()),
});

export const knowledgeBaseSchema = z.object({
  urls: z.array(z.string().url('Invalid URL')).default([]),
  uploaded_files: z.array(z.string()).default([]),
});

export const agentSchema = z.object({
  profile: agentProfileSchema,
  system_prompt: z.string().min(1, 'System prompt is required'),
  model_settings: modelSettingsSchema,
  is_public: z.boolean().default(false),
  knowledge_base: knowledgeBaseSchema,
  tools: z.array(z.string()).default([]),
});

export type AgentFormData = z.infer<typeof agentSchema>;
