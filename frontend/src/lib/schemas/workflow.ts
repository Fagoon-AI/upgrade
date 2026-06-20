import { z } from 'zod';

export const dataMappingSchema = z.object({
  source_field: z.string().default('output'),
  target_field: z.string().default('input'),
  transform: z.string().default('json'),
  default_value: z.string().optional(),
});

export const workflowEdgePayloadSchema = z.object({
  id: z.string(),
  source: z.string(),
  target: z.string(),
  sourceHandle: z.string().default('output'),
  targetHandle: z.string().default('input'),
  data_mappings: z.array(dataMappingSchema).optional(),
  merge_strategy: z.string().default('concatenate'),
  auto_map: z.boolean().default(true),
  label: z.string().optional(),
  animated: z.boolean().default(false),
});

export const workflowNodePayloadSchema = z.object({
  id: z.string(),
  type: z.string(),
  position: z.object({
    x: z.number(),
    y: z.number(),
  }),
  data: z.object({
    label: z.string(),
    inputs: z.record(z.string(), z.any()).optional(),
  }).catchall(z.any()),
});

export const graphDefinitionSchema = z.object({
  nodes: z.array(workflowNodePayloadSchema),
  edges: z.array(workflowEdgePayloadSchema),
  viewport: z.object({
    x: z.number().default(0),
    y: z.number().default(0),
    zoom: z.number().default(1),
  }).optional(),
});

export const createWorkflowSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().default(''),
  graph_definition: graphDefinitionSchema,
});

export type CreateWorkflowPayload = z.infer<typeof createWorkflowSchema>;
export type GraphDefinition = z.infer<typeof graphDefinitionSchema>;
export type WorkflowNodePayload = z.infer<typeof workflowNodePayloadSchema>;
export type WorkflowEdgePayload = z.infer<typeof workflowEdgePayloadSchema>;
export type DataMapping = z.infer<typeof dataMappingSchema>;
