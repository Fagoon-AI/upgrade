import { Node, Edge } from '@xyflow/react';
import { workflowExecutor } from './src/lib/services/workflow-executor';

async function testAdvancedWorkflow() {
  console.log("Setting up advanced workflow graph...");

  const nodes: Node[] = [
    {
      id: 'node-prompt-1',
      type: 'input',
      position: { x: 0, y: 0 },
      data: {
        id: 'user-input',
        inputs: [],
        settings: [{ id: 'inputLabel', default: 'A majestic eagle flying over a mountain range at sunrise' }]
      }
    },
    {
      id: 'node-llm-1',
      type: 'llm',
      position: { x: 200, y: 0 },
      data: {
        id: 'gemini-3.1-pro-preview',
        inputs: [],
        settings: {}
      }
    },
    {
      id: 'node-video-1',
      type: 'video',
      position: { x: 400, y: -100 },
      data: {
        id: 'veo-3.0-generate-001',
        inputs: [],
        settings: {}
      }
    },
    {
      id: 'node-image-1',
      type: 'image',
      position: { x: 400, y: 100 },
      data: {
        id: 'dalle-3', // testing image generation routing
        inputs: [],
        settings: {}
      }
    }
  ];

  const edges: Edge[] = [
    {
      id: 'edge-1',
      source: 'node-prompt-1',
      target: 'node-llm-1',
      targetHandle: 'prompt'
    },
    {
      id: 'edge-2',
      source: 'node-llm-1',
      target: 'node-video-1',
      targetHandle: 'prompt'
    },
    {
      id: 'edge-3',
      source: 'node-llm-1',
      target: 'node-image-1',
      targetHandle: 'prompt'
    }
  ];

  console.log("Executing Advanced Workflow...");
  const result = await workflowExecutor.executeWorkflow(nodes, edges, "", "test_user_123");
  
  console.log("Advanced Workflow Execution Result:");
  console.log(JSON.stringify(result, null, 2));
}

testAdvancedWorkflow().catch(console.error);