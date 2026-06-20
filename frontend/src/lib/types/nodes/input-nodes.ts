import { NodeDefinition } from "./nodes";

export const INPUT_NODE_DEFINITIONS: NodeDefinition[] = [
  {
    id: 'user-input',
    name: 'User Input',
    category: 'input-output',
    description: 'Starting point for workflow input that generates a prompt',
    icon: 'user',
    inputs: [],
    outputs: [
      {
        id: 'prompt',
        name: 'Prompt',
        type: 'prompt',
        description: 'The user provided input as a prompt'
      }
    ],
    settings: [
      {
        id: 'inputLabel',
        name: 'Input Prompt',
        type: 'text',
        description: 'Label to show in the user interface',
        default: 'Enter your prompt here'
      },
    ],
    tags: ['input', 'start', 'user', 'prompt'],
    examples: [
      'Creates a starting point for user to enter text that will be sent to AI models'
    ]
  },
  {
    id: 'file-input',
    name: 'File Input',
    category: 'input-output',
    description: 'Import files into the workflow',
    icon: 'file-input',
    inputs: [],
    outputs: [
      {
        id: 'content',
        name: 'Content',
        type: 'string',
        description: 'The extracted content from the file'
      },
      {
        id: 'prompt',
        name: 'As Prompt',
        type: 'prompt',
        description: 'File content formatted as a prompt for models'
      },
      {
        id: 'metadata',
        name: 'Metadata',
        type: 'object',
        description: 'File metadata including name, size, and type'
      }
    ],
    settings: [
      {
        id: 'file',
        name: 'File',
        type: 'file',
        description: 'file',
      },
    ],
    tags: ['file', 'import', 'document', 'prompt'],
    examples: [
      'Upload a PDF document and extract its text to analyze with GPT-4'
    ]
  },
  {
    id: 'endpoint',
    name: 'Result Output',
    category: 'input-output',
    description: 'Final node to display workflow results',
    icon: 'flag',
    inputs: [
      {
        id: 'input',
        name: 'Input',
        type: 'any',
        description: 'The final workflow result'
      }
    ],
    outputs: [],
    settings: [
      {
        id: 'formatOutput',
        name: 'Format Output',
        type: 'boolean',
        description: 'Apply formatting to the output',
        default: true
      },
      {
        id: 'outputType',
        name: 'Output Type',
        type: 'select',
        options: [
          { label: 'Text', value: 'text' },
          { label: 'JSON', value: 'json' },
          { label: 'HTML', value: 'html' },
          { label: 'Markdown', value: 'markdown' }
        ],
        default: 'text'
      }
    ],
    tags: ['output', 'result', 'final', 'display'],
    examples: [
      'Display the final generated text from an AI model'
    ]
  },
  {
    id: 'webhook-output',
    name: 'Webhook Output',
    category: 'input-output',
    description: 'Send workflow results to an external webhook',
    icon: 'webhook',
    inputs: [
      {
        id: 'data',
        name: 'Data',
        type: 'any',
        description: 'Data to send to the webhook'
      }
    ],
    outputs: [
      {
        id: 'response',
        name: 'Response',
        type: 'object',
        description: 'Response from the webhook'
      },
      {
        id: 'responsePrompt',
        name: 'Response As Prompt',
        type: 'prompt',
        description: 'Webhook response formatted as a prompt'
      }
    ],
    settings: [
      {
        id: 'url',
        name: 'Webhook URL',
        type: 'text',
        required: true,
        placeholder: 'https://example.com/webhook'
      },
      {
        id: 'method',
        name: 'HTTP Method',
        type: 'select',
        options: [
          { label: 'POST', value: 'POST' },
          { label: 'PUT', value: 'PUT' },
          { label: 'PATCH', value: 'PATCH' },
          { label: 'GET', value: 'GET' }
        ],
        default: 'POST'
      },
      {
        id: 'headers',
        name: 'Headers',
        type: 'json',
        default: '{"Content-Type": "application/json"}'
      },
      {
        id: 'responseAsPrompt',
        name: 'Format Response as Prompt',
        type: 'boolean',
        description: 'Convert webhook response to a prompt format',
        default: false
      },
      {
        id: 'promptTemplate',
        name: 'Response Template',
        type: 'textarea',
        description: 'Template for formatting response as prompt. Use {{response}} to reference the response data.',
        placeholder: 'API returned: {{response}}',
        rows: 3,
        visibility: 'responseAsPrompt'
      }
    ],
    tags: ['webhook', 'http', 'api', 'integration'],
    examples: [
      'Send generated content to an external API endpoint'
    ]
  },
  {
    id: 'api-input',
    name: 'API Input',
    category:'input-output',
    description: 'Initial Data for API calls',
    icon: 'brain',
    inputs: [
    ],
    outputs: [
      {
        id: 'response',
        name: 'Response',
        type: 'string',
        description: 'Initial Data for API calls'
      }
    ],
    settings:[]

  },
]