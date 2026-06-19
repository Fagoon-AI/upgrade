
import { NodeDefinition } from "./nodes";

export const LANGUAGE_NODE_DEFINITIONS: NodeDefinition[] = [
  {
    id: 'gpt-4',
    name: 'GPT-4',
    category: 'language-models',
    description: 'Advanced language model for complex tasks',
    icon: 'brain',
    inputs: [
      {
        id: 'prompt',
        name: 'Prompt',
        type: 'prompt',
        description: 'The input prompt for the model',
        required: true
      },
      {
        id: 'systemPrompt',
        name: 'System Prompt',
        type: 'prompt',
        description: 'System instructions for the model',
        required: false
      },
      {
        id: 'context',
        name: 'Context',
        type: 'array',
        description: 'Additional context documents for the model',
        required: false,
        allowMultiple: true
      }
    ],
    outputs: [
      {
        id: 'response',
        name: 'Response',
        type: 'string',
        description: 'The model\'s response'
      }
    ],
    settings: [
      {
        id: 'model',
        name: 'Model Version',
        type: 'select',
        options: [
          { label: 'GPT-4o', value: 'gpt-4o' },
          { label: 'GPT-4 Turbo', value: 'gpt-4-turbo' },
          { label: 'GPT-4', value: 'gpt-4' }
        ],
        default: 'gpt-4o'
      },
      {
        id: 'temperature',
        name: 'Temperature',
        type: 'range',
        description: 'Controls randomness in the output',
        default: 0.7,
        min: 0,
        max: 2,
        step: 0.1
      },
      {
        id: 'maxTokens',
        name: 'Max Tokens',
        type: 'number',
        description: 'Maximum number of tokens to generate',
        default: 1000,
        min: 50,
        max: 8192
      },
      {
        id: 'topP',
        name: 'Top P',
        type: 'range',
        description: 'Nucleus sampling threshold',
        default: 1,
        min: 0.1,
        max: 1,
        step: 0.05
      },
    ],
    tags: ['language', 'openai', 'gpt', 'chat', 'ai'],
    version: '1.1.0',
    author: 'OpenAI',
    examples: [
      'Generate a detailed analysis of a text',
      'Create code based on specifications',
      'Answer complex questions with nuanced reasoning'
    ]
  },
  {
    id: 'gpt-3.5-turbo',
    name: 'GPT-3.5 Turbo',
    category: 'language-models',
    description: 'Fast and efficient language model for everyday tasks',
    icon: 'cpu',
    inputs: [
      {
        id: 'prompt',
        name: 'Prompt',
        type: 'prompt',
        required: true
      },
      {
        id: 'systemPrompt',
        name: 'System Prompt',
        type: 'prompt',
        required: false
      },
      {
        id: 'context',
        name: 'Context',
        type: 'array',
        description: 'Additional context documents',
        required: false,
        allowMultiple: true
      }
    ],
    outputs: [
      {
        id: 'response',
        name: 'Response',
        type: 'string'
      }
    ],
    settings: [
      {
        id: 'temperature',
        name: 'Temperature',
        type: 'range',
        default: 0.7,
        min: 0,
        max: 2,
        step: 0.1
      },
      {
        id: 'maxTokens',
        name: 'Max Tokens',
        type: 'number',
        default: 1000,
        min: 50,
        max: 4096
      },
    ],
    tags: ['language', 'openai', 'gpt', 'chat', 'efficient', 'ai'],
    version: '1.1.0',
    author: 'OpenAI',
    examples: [
      'Generate short summaries of text',
      'Answer straightforward questions',
      'Help with simple writing tasks'
    ]
  },
  {
    id: 'claude-3',
    name: 'Claude3',
    category: 'language-models',
    description: 'Claudes\'s open-source large language model',
    icon: 'claude',
    inputs: [
      {
        id: 'prompt',
        name: 'Prompt',
        type: 'prompt',
        required: true
      },
      {
        id: 'systemPrompt',
        name: 'System Prompt',
        type: 'prompt',
        required: false,
        description: 'System instructions for the model'
      }
    ],
    outputs: [
      {
        id: 'response',
        name: 'Response',
        type: 'string'
      }
    ],
    settings: [
      {
        id: 'model',
        name: 'Model Size',
        type: 'select',
        options: [
          { label: '8B', value: '8b' },
          { label: '70B', value: '70b' }
        ],
        default: '70b'
      },
      {
        id: 'temperature',
        name: 'Temperature',
        type: 'range',
        default: 0.7,
        min: 0,
        max: 1,
        step: 0.05
      },
      {
        id: 'maxTokens',
        name: 'Max Tokens',
        type: 'number',
        default: 1024,
        min: 50,
        max: 4096
      },
    ],
    tags: ['language', 'meta', 'open-source', 'llama', 'ai'],
    version: '1.1.0',
    author: 'Meta',
    examples: [
      'Generate creative content with an open-source model',
      'Process text with a locally deployable AI'
    ]
  },
  {
    id: 'llama-3',
    name: 'Llama 3',
    category: 'language-models',
    description: 'Meta\'s open-source large language model',
    icon: 'meta',
    inputs: [
      {
        id: 'prompt',
        name: 'Prompt',
        type: 'prompt',
        required: true
      },
      {
        id: 'systemPrompt',
        name: 'System Prompt',
        type: 'prompt',
        required: false,
        description: 'System instructions for the model'
      }
    ],
    outputs: [
      {
        id: 'response',
        name: 'Response',
        type: 'string'
      }
    ],
    settings: [
      {
        id: 'model',
        name: 'Model Size',
        type: 'select',
        options: [
          { label: '8B', value: '8b' },
          { label: '70B', value: '70b' }
        ],
        default: '70b'
      },
      {
        id: 'temperature',
        name: 'Temperature',
        type: 'range',
        default: 0.7,
        min: 0,
        max: 1,
        step: 0.05
      },
      {
        id: 'maxTokens',
        name: 'Max Tokens',
        type: 'number',
        default: 1024,
        min: 50,
        max: 4096
      },
    ],
    tags: ['language', 'meta', 'open-source', 'llama', 'ai'],
    version: '1.1.0',
    author: 'Meta',
    examples: [
      'Generate creative content with an open-source model',
      'Process text with a locally deployable AI'
    ]
  },

  {
    id: 'web-search',
    name: 'Web Search',
    category: 'language-models',
    description: 'Search the web for data',
    icon: 'meta',
    inputs: [
      {
        id: 'prompt',
        name: 'Prompt',
        type: 'prompt',
        required: true
      },
      {
        id:'url',
        name:'url',
        type:'prompt',
        required: true
      }
    ],
    outputs: [
      {
        id: 'response',
        name: 'Response',
        type: 'string'
      }
    ],
    settings: [
    ],
    tags: ['language', 'meta', 'open-source', 'llama', 'ai'],
    version: '1.1.0',
    author: 'Meta',
    examples: [
      'Find the top 10 top scorers in Laliga this season'
    ]
  },
  {
    id: 'nano-banana-pro-preview',
    name: 'Google Nano Banana',
    category: 'language-models',
    description: 'Lightweight and highly capable edge/pro model from Google',
    icon: 'google',
    inputs: [
      { id: 'prompt', name: 'Prompt', type: 'prompt', required: true },
      { id: 'systemPrompt', name: 'System Prompt', type: 'prompt', required: false, description: 'System instructions for the model' },
      { id: 'context', name: 'Context', type: 'array', description: 'Additional context documents for the model', required: false }
    ],
    outputs: [
      { id: 'response', name: 'Response', type: 'string' }
    ],
    settings: [],
    tags: ['language', 'google', 'nano', 'banana', 'ai'],
    version: '1.0.0',
    author: 'Google',
    examples: []
  },
  {
    id: 'gemini-3.1-pro-preview',
    name: 'Gemini 3.1 Pro',
    category: 'language-models',
    description: 'Next-generation Gemini Pro from Google',
    icon: 'google',
    inputs: [
      { id: 'prompt', name: 'Prompt', type: 'prompt', required: true },
      { id: 'systemPrompt', name: 'System Prompt', type: 'prompt', required: false, description: 'System instructions for the model' },
      { id: 'context', name: 'Context', type: 'array', description: 'Additional context documents for the model', required: false }
    ],
    outputs: [
      { id: 'response', name: 'Response', type: 'string' }
    ],
    settings: [],
    tags: ['language', 'google', 'gemini', 'ai'],
    version: '1.0.0',
    author: 'Google',
    examples: []
  }
];
