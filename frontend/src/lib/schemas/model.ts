import { z } from "zod";

export enum Provider {
    OPENAI = "openai",
    GEMINI = "gemini",
    HUGGING_FACE = "hugging_face",
    GROQ = "groq",
    ANTHROPIC = "anthropic",
    PERPLEXITY = "perplexity",
    LOCALHOST = "localhost"
}

export enum Feature {
    CHAT = "chat",
    AGENTS = "agents",
    WORKFLOW = "workflow",
    VIBE_CODER = "vibe_coder"
}

export const ModelConfigSchema = z.object({
    name: z.string(),
    provider: z.nativeEnum(Provider),
    model_id: z.string(),
    api_key: z.string().optional(),
    features: z.array(z.nativeEnum(Feature)),
    agent_ids: z.array(z.string()),
    workflow_ids: z.array(z.string()),
});

export type ModelConfig = z.infer<typeof ModelConfigSchema>;

export interface ModelResponse {
    id: string;
    name: string;
    provider: Provider;
    model_id: string;
    masked_api_key: string;
    features: Feature[];
    agent_ids: string[];
    workflow_ids: string[];
    is_enabled: boolean;
    created_at: string;
    updated_at: string;
}