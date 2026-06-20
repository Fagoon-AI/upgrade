export type AIModelType = 'llm' | 'diffusion' | 'voice' | 'memory' | 'output';

export interface AIModel {
  id: string;
  name: string;
  type: AIModelType;
  description: string;
  version?: string;
}

export const AI_MODELS: AIModel[] = [
  {
    id: 'gpt-4',
    name: 'GPT-4',
    type: 'llm',
    description: 'Advanced language model for complex tasks',
    version: '4.0'
  },
  {
    id: 'gpt-3.5-turbo',
    name: 'GPT-3.5 Turbo',
    type: 'llm',
    description: 'Fast and efficient language model',
    version: '3.5'
  },
  {
    id: 'stable-diffusion-xl',
    name: 'Stable Diffusion XL',
    type: 'diffusion',
    description: 'High-quality image generation',
    version: 'XL'
  },
  {
    id: 'dall-e-3',
    name: 'DALL·E 3',
    type: 'diffusion',
    description: 'Advanced image generation from OpenAI',
    version: '3'
  },
  {
    id: 'elevenlabs',
    name: 'ElevenLabs',
    type: 'voice',
    description: 'High-quality voice synthesis',
    version: '1.0'
  },
  {
    id: 'nano-banana-pro-preview',
    name: 'Google Nano Banana',
    type: 'llm',
    description: 'Lightweight and highly capable edge/pro model from Google',
    version: 'Pro'
  },
  {
    id: 'gemini-3.1-pro-preview',
    name: 'Gemini 3.1 Pro',
    type: 'llm',
    description: 'Next-generation Gemini Pro from Google',
    version: '3.1'
  },
  {
    id: 'veo-3.0-generate-001',
    name: 'Veo 3 Video Gen',
    type: 'diffusion',
    description: 'Google Veo 3 Video Generation',
    version: '3.0'
  }
];

export interface WorkflowNode {
  id: string;
  type: AIModelType;
  position: { x: number; y: number };
  data: {
    label: string;
    modelId?: string;
    settings?: Record<string, any>;
  };
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
}

export interface IWorkflowHistoryItem {
  _id: string
  executedFrom: 'MANUAL' | 'API' | 'SCHEDULED'
  result: string
  status: 'COMPLETED' | 'FAILED'
  time: string
  workflow: {
    published: boolean
    _id: string
    id: string
    name: string
    updatedAt: string
    createdAt: string
  }
}

export interface ValidationResult {
  isValid: boolean;
  message?: string;
}

export const validateConnection = (
  source: WorkflowNode,
  target: WorkflowNode
): ValidationResult => {
  // Both nodes must have models selected
  if (!source.data.modelId || !target.data.modelId) {
    return {
      isValid: false,
      message: 'Both nodes must have models selected'
    };
  }

  // Output nodes can receive connections from any node
  if (target.type === 'output') {
    return { isValid: true };
  }

  // Memory nodes can connect to any node type
  if (source.type === 'memory' || target.type === 'memory') {
    return { isValid: true };
  }

  // LLM can connect to Diffusion or Voice
  if (source.type === 'llm' && (target.type === 'diffusion' || target.type === 'voice')) {
    return { isValid: true };
  }

  // Diffusion can connect to LLM for image analysis
  if (source.type === 'diffusion' && target.type === 'llm') {
    return { isValid: true };
  }

  return {
    isValid: false,
    message: 'Invalid connection between these model types'
  };
};

export interface BackendWorkflow {
  id: string;
  name: string;
  description: string;
  status: string;
  version: number;
  active_version_id?: string;
  node_count?: number;
  edge_count?: number;
  is_runnable?: boolean;
  graph_definition?: {
    nodes: any[];
    edges: any[];
    viewport?: {
      x: number;
      y: number;
      zoom: number;
    };
  };
  global_variables?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

export interface GetWorkflowsResponse {
  success: boolean;
  message: string;
  data: BackendWorkflow[];
  meta?: {
    total: number;
    skip: number;
    limit: number;
    has_more: boolean;
  };
  timestamp?: string;
}