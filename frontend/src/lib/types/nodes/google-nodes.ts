

import { NodeDefinition } from "./nodes";

export const GOOGLE_NODE_DEFINITIONS: NodeDefinition[] = [
  {
    id: 'send-email',
    name: 'Send Email',
    category: 'google-workspace',
    description: 'Send an email using Google Workspace',
    icon: 'mail',
    actionHeader:'email',
    inputs: [
      {
        id: 'to',
        name: 'To',
        type: 'string',
        description: 'Recipient email address',
        required: true
      },
      {
        id: 'subject',
        name: 'Subject',
        type: 'string',
        description: 'Email subject line',
        required: true
      },
      {
        id: 'body',
        name: 'Body',
        type: 'string',
        description: 'Email body content',
        required: true
      },
    ],
    outputs: [
      {
        id: 'response',
        name: 'Response',
        type: 'string',
        description: 'Response from the email service'
      }
    ],
    settings: [
    ],
    tags: ['input', 'start', 'user', 'prompt'],
    examples: [
      'Creates a starting point for user to enter text that will be sent to AI models'
    ]
  },
  {
    id: 'reply-email',
    name: 'Reply Email',
    category: 'google-workspace',
    description: 'Reply to an email using Google Workspace',
    icon: 'mail',
    actionHeader:'email',
    inputs: [
      {
        id: 'to',
        name: 'To',
        type: 'string',
        description: 'Recipient email address',
        required: true
      },
      {
        id: 'subject',
        name: 'Subject',
        type: 'string',
        description: 'Email subject line',
        required: true
      },
      {
        id: 'body',
        name: 'Body',
        type: 'string',
        description: 'Email body content',
        required: true
      },
      {
        id:'original_message_id',
        name:'Conversation ID',
        type:'string',
        description: 'ID of the email conversation to reply to',
        required: true
      }
    ],
    outputs: [
      {
        id: 'response',
        name: 'Response',
        type: 'string',
        description: 'Response from the email service'
      }
    ],
    settings: [
    ],
    tags: ['input', 'start', 'user', 'prompt'],
    examples: [
      'Creates a starting point for user to enter text that will be sent to AI models'
    ]
  },
  {
    id: 'summarise-email',
    name: 'Summarise Email',
    category: 'google-workspace',
    description: 'Summarise Emails',
    icon: 'mail',
    actionHeader:'email',
    inputs: [
      {
        id:'message_id',
        name:'Conversation ID',
        type:'string',
        description: 'ID of the email conversation to reply to',
        required: true
      }
    ],
    outputs: [
      {
        id: 'response',
        name: 'Response',
        type: 'string',
        description: 'Response from the email service'
      }
    ],
    settings: [
    ],
    tags: ['input', 'start', 'user', 'prompt'],
    examples: [
      'Creates a starting point for user to enter text that will be sent to AI models'
    ]
  },
  {
    id: 'get-email-details',
    name: 'Get Email Details',
    category: 'google-workspace',
    description: 'Get details of a single email',
    icon: 'mail',
    actionHeader:'email',
    inputs: [
      {
        id:'message_id',
        name:'Conversation ID',
        type:'string',
        description: 'ID of the email conversation to reply to',
        required: true
      }
    ],
    outputs: [
      {
        id: 'response',
        name: 'Response',
        type: 'string',
        description: 'Response from the email service'
      }
    ],
    settings: [
      {
        id: 'number-of-emails',
        name: 'Number of Emails',
        type: 'number',
        default:0
      }
    ],
    tags: ['input', 'start', 'user', 'prompt'],
    examples: [
      'Creates a starting point for user to enter text that will be sent to AI models'
    ]
  },
    {
    id: 'create-docs',
    name: 'Create Google Docs',
    category: 'google-workspace',
    description: 'Create a new Google Docs file',
    icon: 'mail',
    actionHeader:'docs',
    inputs: [
      {
        id:'title',
        name:'Docs Title',
        type:'string',
        description: 'Title of the docs file',
        required: false
      },
      {
        id:'initial_content',
        name:'Initial Content',
        type:'string',
        description: 'Initial Content of the docs',
        required: false
      }
    ],
    outputs: [
      {
        id: 'docs_id',
        name: 'Docs Id',
        type: 'string',
        description: 'Id of the created docs'
      },
    ],
    settings: [],
    tags: ['input', 'start', 'user', 'prompt'],
    examples: [
      'Creates a starting point for user to enter text that will be sent to AI models'
    ]
  },
  {
    id: 'get-docs-content',
    name: 'Get Docs Content',
    category: 'google-workspace',
    description: 'Get Content of the docs',
    icon: 'mail',
    actionHeader:'docs',
    inputs: [
      {
        id:'document_id',
        name:'Docs Id',
        type:'string',
        description: 'Id of the docs file',
        required: true
      },
    ],
    outputs: [
      {
        id: 'content',
        name: 'Content',
        type: 'string',
        description: 'Content of the docs'
      },
    ],
    settings: [],
    tags: ['input', 'start', 'user', 'prompt'],
    examples: [
      'Creates a starting point for user to enter text that will be sent to AI models'
    ]
  },
  {
    id: 'write-docs-content',
    name: 'Write Docs Content',
    category: 'google-workspace',
    description: 'Write Content to the docs',
    icon: 'mail',
    actionHeader:'docs',
    inputs: [
      {
        id:'document_id',
        name:'Docs Id',
        type:'string',
        description: 'Id of the docs file',
        required: true
      },
      {
        id:'text_content',
        name:'Text Content',
        type:'string',
        description:'Text to be inserted',
        required:true
      }
    ],
    outputs: [
      {
        id: 'content',
        name: 'Content',
        type: 'string',
        description: 'Content of the docs'
      },
    ],
    settings: [],
    tags: ['input', 'start', 'user', 'prompt'],
    examples: [
      'Creates a starting point for user to enter text that will be sent to AI models'
    ]
  },
 {
    id: 'create-drive-folder',
    name: 'Create Folder ',
    category: 'google-workspace',
    description: 'Create a folder in Google Drive',
    icon: 'mail',
    actionHeader:'drive',
    inputs: [
      {
        id:'folder_name',
        name:'Docs Id',
        type:'string',
        description: 'Id of the docs file',
        required: true
      },
      {
        id:'parent_id',
        name:'Text Content',
        type:'string',
        description:'Text to be inserted',
        required:false
      }
    ],
    outputs: [
      {
        id: 'folder_id',
        name: 'Folder Id',
        type: 'string',
        description: 'Content of the docs'
      },
    ],
    settings: [],
    tags: ['input', 'start', 'user', 'prompt'],
    examples: [
      'Creates a starting point for user to enter text that will be sent to AI models'
    ]
  },

]