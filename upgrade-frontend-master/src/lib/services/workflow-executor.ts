import {  Edge, Node } from '@xyflow/react'; // Updated from react-flow-renderer
import {
  ExecutionStatus,
  NodeExecutionData,
  WorkflowExecution,
  nodeExecutors
} from '@/lib/types/execution/execution';
import axios from 'axios';
import { NodeDefinition } from '../types/nodes/nodes';

export class WorkflowExecutor {
  private execution: WorkflowExecution | null = null;
  private pendingInputsCount: Record<string, number> = {};

  async executeWorkflow(nodes: Node[], edges: Edge[], userInput: string, user_id: string): Promise<WorkflowExecution> {
    this.execution = {
      id: `exec-${Date.now()}`,
      status: 'running',
      startTime: new Date(),
      nodes: {}
    };
    
    this.pendingInputsCount = {};
    for (const node of nodes) {
      const incoming = edges.filter(e => e.target === node.id).length;
      this.pendingInputsCount[node.id] = incoming;
    }
    
    try {
      const startNodes = nodes.filter(node =>
        !edges.some(edge => edge.target === node.id)
      );

      //if no start node because of loop, do thisL
      if(startNodes.length === 0) {
        await this.executeNode(nodes[0], nodes, edges, userInput, user_id);
      }

      // if start loop:
      for (const startNode of startNodes) {
        await this.executeNode(startNode, nodes, edges, userInput, user_id);
      }
      
      this.execution.status = 'completed';
      this.execution.endTime = new Date();
      
    } catch (error) {
      this.execution.status = 'error';
      this.execution.endTime = new Date();
      this.execution.error = error instanceof Error ? error.message : 'Unknown error';
    }
    
    return this.execution;
  }

  private async executeNode(
    node: Node,
    allNodes: Node[],
    allEdges: Edge[],
    userInput: string,
    user_id: string
  ): Promise<void> {
    if (!this.execution) return;
    
    this.execution.nodes[node.id] = {
      id: node.id,
      status: 'running',
      input: {}
    };
    
    try {
      const inputEdges = allEdges.filter(edge => edge.target === node.id);
      const inputs = await this.gatherInputs(inputEdges, allNodes, userInput, node.id);

      const nodeType = node.data.id || '';
      const executor = nodeExecutors[nodeType];
      if (!executor) throw new Error(`No executor found for node type: ${nodeType}`);
      
      const result = await executor(inputs, node.data.settings || {}, user_id);
      
      this.execution.nodes[node.id].status = 'completed';
      this.execution.nodes[node.id].output = result.data;
      
      const outputEdges = allEdges.filter(edge => edge.source === node.id);
      for (const edge of outputEdges) {
        const nextNodeId = edge.target;
        this.pendingInputsCount[nextNodeId]--;

        if (this.pendingInputsCount[nextNodeId] === 0) {
          const nextNode = allNodes.find(n => n.id === nextNodeId);
          if (nextNode) {
            await this.executeNode(nextNode, allNodes, allEdges, userInput, user_id);
          }
        }
      }
    } catch (error) {
      this.execution.nodes[node.id].status = 'error';
      this.execution.nodes[node.id].error = error instanceof Error ? error.message : 'Unknown error';
    }
  }

// eslint-disable-next-line @typescript-eslint/no-explicit-any
private async gatherInputs(edges: Edge[], nodes: Node[], userInput: string, node_id: string): Promise<Record<string, any>> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const inputs: Record<string, any> = { userInput };
// if(edges.length >0){

  for (const edge of edges) {
    const sourceNode = nodes.find(n => n.id === edge.source);
    if (!sourceNode) continue;
    
    const isPromptNode = sourceNode.id.includes('prompt');
    const value = isPromptNode
      ? sourceNode.data.default || sourceNode.data?.settings?.[0]?.default
      : this.execution?.nodes[sourceNode.id]?.output;
      
      if (value !== undefined && value !== 'undefined') {
        console.log('hawa siriririri')
        const key = edge.targetHandle || 'default';
        inputs[key] = inputs[key] ? inputs[key] + value : value;
      }
    }
  // }else{
    const currentNode = nodes.find(n => n.id == node_id);
    
    currentNode?.data?.inputs.forEach(i=>{
      if(i.default){
        inputs[i.id] = inputs[i.id]? inputs[i.id]+ i.default: i.default 
      }
    })
  // }
  return inputs;
}

  getCurrentExecution(): WorkflowExecution | null {
    return this.execution;
  }
}

export const workflowExecutor = new WorkflowExecutor();