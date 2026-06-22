/* eslint-disable @typescript-eslint/no-explicit-any */

// Node Categories
export type NodeCategory = string;

// Port data types with improved documentation
export type PortDataType =
  'string' |
  'number' |
  'boolean' |
  'object' |
  'array' |
  'image' |
  'audio' |
  'vector' |
  'file' |
  'prompt' |  // New type specifically for prompts
  'any';

// Setting types
export type SettingType =
  'text' |
  'number' |
  'select' |
  'boolean' |
  'json' |
  'code' |
  'file' |
  'color' |
  'range' |
  'textarea' |
  'credential' |
  'connection';

export type ActionHeaderType = 'email' | 'docs' | 'drive';

export interface NodeDefinition {
  id: string;
  name: string;
  category: NodeCategory;
  description: string;
  icon: string;
  inputs: NodePort[];
  actionHeader?: ActionHeaderType
  outputs: NodePort[];
  settings: NodeSetting[];
  tags?: string[];
  documentation?: string;
  author?: string;
  version?: string;
  examples?: string[]; // New field for usage examples
}
export interface NodeInput {
  id: string;
  name: string;
  type: PortDataType;
  description?: string;
  required?: boolean;
  defaultValue?: any;
}
export interface NodePort {
  id: string;
  name: string;
  type: PortDataType;
  description?: string;
  required?: boolean;
  allowMultiple?: boolean;
  default?: any; // New field for default value
}

export interface NodeSetting {
  id: string;
  name: string;
  label: string;
  type: SettingType;
  description?: string;
  default?: any;
  options?: { label: string; value: any }[];
  required?: boolean;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
  rows?: number;
  language?: string; // For code editor
  dependsOn?: string; // New field for conditional settings
  visibility?: string; // New field for conditional visibility
}

export const ACTION_HEADERS: { id: ActionHeaderType, category: NodeCategory }[] = [
  {
    id: 'email',
    category: 'google-workspace'
  },
  {
    id: 'docs',
    category: 'google-workspace'
  },
  {
    id: 'drive',
    category: 'google-workspace'
  }
];

export const NODE_CATEGORIES: Record<string, string> = {};
export const NODE_DEFINITIONS: NodeDefinition[] = [];

export interface NodeField {
  name: string;
  label: string;
  type:
  | "connection_select"
  | "select"
  | "textarea"
  | "slider"
  | "number";
  required: boolean;
  placeholder?: string;
  description?: string;
  default?: string | number;
  options?: string[];
}

export interface WorkflowNodeDefinition {
  type: string;
  display_name: string;
  icon: string;
  category: string;
  description: string;
  fields: NodeField[];
  outputs: string[];
}