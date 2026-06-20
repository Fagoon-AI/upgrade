

import { NodeDefinition } from "./nodes";

export const IMAGEGEN_NODE_DEFINITIONS: NodeDefinition[] = [
  {
    id: 'stable-diffusion-xl',
    name: 'Stable Diffusion XL',
    category: 'diffusion-models',
    description: 'Generate high-quality images from text descriptions',
    icon: 'image',
    inputs: [
      {
        id: 'prompt',
        name: 'Prompt',
        type: 'prompt',
        required: true
      },
      {
        id: 'negativePrompt',
        name: 'Negative Prompt',
        type: 'prompt',
        required: false
      },
      {
        id: 'seed',
        name: 'Seed Image',
        type: 'image',
        required: false,
        description: 'Optional starting image for img2img generation'
      }
    ],
    outputs: [
      {
        id: 'image',
        name: 'Generated Image',
        type: 'image'
      }
    ],
    settings: [
      {
        id: 'steps',
        name: 'Steps',
        type: 'number',
        default: 50,
        min: 10,
        max: 150
      },
      {
        id: 'guidance',
        name: 'Guidance Scale',
        type: 'range',
        default: 7.5,
        min: 1,
        max: 15,
        step: 0.5
      },
      {
        id: 'dimensions',
        name: 'Dimensions',
        type: 'select',
        options: [
          { label: '512×512', value: '512x512' },
          { label: '768×768', value: '768x768' },
          { label: '1024×1024', value: '1024x1024' },
          { label: '1024×768', value: '1024x768' },
          { label: '768×1024', value: '768x1024' }
        ],
        default: '1024x1024'
      },
      {
        id: 'seed',
        name: 'Random Seed',
        type: 'number',
        description: 'Seed for reproducible results (0 for random)',
        default: 0
      }
    ],
    tags: ['image', 'generation', 'diffusion', 'stable-diffusion', 'ai'],
    version: '1.1.0',
    author: 'StabilityAI',
    examples: [
      'Generate a photorealistic landscape image',
      'Create concept art for characters or environments',
      'Convert a sketch to a detailed illustration'
    ]
  },
  {
    id: 'dalle-3',
    name: 'DALL·E 3',
    category: 'diffusion-models',
    description: 'OpenAI\'s latest powerful image generation model',
    icon: 'paintbrush',
    inputs: [
      {
        id: 'prompt',
        name: 'Prompt',
        type: 'prompt',
        required: true
      },
      {
        id: 'reference',
        name: 'Reference Image',
        type: 'image',
        required: false,
        description: 'Optional reference image for variations'
      }
    ],
    outputs: [
      {
        id: 'image',
        name: 'Generated Image',
        type: 'image'
      }
    ],
    settings: [
      {
        id: 'quality',
        name: 'Quality',
        type: 'select',
        options: [
          { label: 'Standard', value: 'standard' },
          { label: 'HD', value: 'hd' }
        ],
        default: 'standard'
      },
      {
        id: 'style',
        name: 'Style',
        type: 'select',
        options: [
          { label: 'Vivid', value: 'vivid' },
          { label: 'Natural', value: 'natural' }
        ],
        default: 'vivid'
      },
      {
        id: 'size',
        name: 'Size',
        type: 'select',
        options: [
          { label: '1024×1024', value: '1024x1024' },
          { label: '1024×1792', value: '1024x1792' },
          { label: '1792×1024', value: '1792x1024' }
        ],
        default: '1024x1024'
      },
      {
        id: 'enhancePrompt',
        name: 'Enhance Prompt',
        type: 'boolean',
        description: 'Allow DALL-E to enhance the prompt for better results',
        default: true
      },
      {
        id: 'n',
        name: 'Number of Images',
        type: 'number',
        description: 'Number of images to generate',
        default: 1,
        min: 1,
        max: 4
      }
    ],
    tags: ['image', 'generation', 'openai', 'dalle', 'ai'],
    version: '1.1.0',
    author: 'OpenAI',
    examples: [
      'Generate a photorealistic product mockup',
      'Create detailed illustrations based on text descriptions'
    ]
  },
  // {
  //   id: 'midjourney',
  //   name: 'Midjourney',
  //   category: 'diffusion-models',
  //   description: 'Create stunning artistic images with detailed prompts',
  //   icon: 'palette',
  //   inputs: [
  //     {
  //       id: 'prompt',
  //       name: 'Prompt',
  //       type: 'string'
  //     },
  //     {
  //       id: 'referenceImage',
  //       name: 'Reference Image',
  //       type: 'image',
  //       required: false
  //     }
  //   ],
  //   outputs: [
  //     {
  //       id: 'image',
  //       name: 'Generated Image',
  //       type: 'image'
  //     }
  //   ],
  //   settings: [
  //     {
  //       id: 'version',
  //       name: 'Version',
  //       type: 'select',
  //       options: [
  //         { label: 'V6', value: 'v6' },
  //         { label: 'V5.2', value: 'v5.2' },
  //         { label: 'V5.1', value: 'v5.1' }
  //       ],
  //       default: 'v6'
  //     },
  //     {
  //       id: 'stylize',
  //       name: 'Stylize',
  //       type: 'range',
  //       min: 0,
  //       max: 1000,
  //       step: 50,
  //       default: 100
  //     },
  //     {
  //       id: 'quality',
  //       name: 'Quality',
  //       type: 'range',
  //       min: 0.25,
  //       max: 2,
  //       step: 0.25,
  //       default: 1
  //     },
  //     {
  //       id: 'aspectRatio',
  //       name: 'Aspect Ratio',
  //       type: 'select',
  //       options: [
  //         { label: '1:1', value: '1:1' },
  //         { label: '16:9', value: '16:9' },
  //         { label: '9:16', value: '9:16' },
  //         { label: '4:3', value: '4:3' },
  //         { label: '3:4', value: '3:4' }
  //       ],
  //       default: '1:1'
  //     }
  //   ],
  //   tags: ['image', 'generation', 'art', 'midjourney'],
  //   version: '1.0.0',
  //   author: 'Midjourney'
  // },
{
    id: 'video-gen',
    name: 'Video Generation',
    category: 'diffusion-models',
    description: 'Generate high-quality video from text descriptions',
    icon: 'video',
    inputs: [
      {
        id: 'prompt',
        name: 'Prompt',
        type: 'prompt',
        required: true
      }
    ],
    outputs: [
      {
        id: 'video',
        name: 'Generated Video',
        type: 'image'
      }
    ],
    settings: [
      {
        id: 'steps',
        name: 'Steps',
        type: 'number',
        default: 50,
        min: 10,
        max: 150
      },
      {
        id: 'guidance',
        name: 'Guidance Scale',
        type: 'range',
        default: 7.5,
        min: 1,
        max: 15,
        step: 0.5
      },
      {
        id: 'dimensions',
        name: 'Dimensions',
        type: 'select',
        options: [
          { label: '512×512', value: '512x512' },
          { label: '768×768', value: '768x768' },
          { label: '1024×1024', value: '1024x1024' },
          { label: '1024×768', value: '1024x768' },
          { label: '768×1024', value: '768x1024' }
        ],
        default: '1024x1024'
      },
      {
        id: 'seed',
        name: 'Random Seed',
        type: 'number',
        description: 'Seed for reproducible results (0 for random)',
        default: 0
      }
    ],
    tags: ['image', 'generation', 'diffusion', 'stable-diffusion', 'ai'],
    version: '1.1.0',
    author: 'StabilityAI',
    examples: [
      'Generate a photorealistic landscape image',
      'Create concept art for characters or environments',
      'Convert a sketch to a detailed illustration'
    ]
  },
  {
    id: 'veo-3.0-generate-001',
    name: 'Veo 3 Video Gen',
    category: 'diffusion-models',
    description: 'Google Veo 3 Video Generation',
    icon: 'google',
    inputs: [
      { id: 'prompt', name: 'Prompt', type: 'prompt', required: true }
    ],
    outputs: [
      { id: 'response', name: 'Response', type: 'string' }
    ],
    settings: [],
    tags: ['video', 'google', 'veo', 'ai'],
    version: '3.0.0',
    author: 'Google',
    examples: []
  }
];
