

import { NodeDefinition } from "./nodes";

export const UTILS_NODE_DEFINITIONS: NodeDefinition[] = [
  {
    id: 'bg-remover',
    name: 'Background Remover',
    category: 'utilities',
    description: 'Remove background from images',
    icon: 'eraser',
    inputs: [
      {
        id: 'file',
        name: 'File',
        type: 'string'
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
    tags: ['text', 'processing', 'chunking', 'utility']
  },
]