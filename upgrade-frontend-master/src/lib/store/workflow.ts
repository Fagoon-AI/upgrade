/* eslint-disable @typescript-eslint/no-explicit-any */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { produce } from 'immer';
import { Node, Edge } from '@xyflow/react';
import { NodeDefinition, NodeCategory, SettingType, NodePort, NodeSetting, WorkflowNodeDefinition } from '@/lib/types/nodes/nodes';
import { WorkflowExecution } from '@/lib/types/execution/execution';
import { showSuccessToast, showErrorToast } from "@/utils/toast";
import { getNodesRegistry, runWorkflow } from '../api/workflow';
import axiosInstance from '../api/axios';
interface WorkflowState {
  nodes: Node[];
  edges: Edge[];
  nodeDefinitions: WorkflowNodeDefinition[];
  selectedNodeId: string | null;
  isCurrentExecutionSavedId: string | null;
  currentWorkflowName: string | null;
  selectedEdgeId: string | null;
  isRunning: boolean;
  userInput: string;
  currentExecution: WorkflowExecution | null;
  savedWorkflows: {
    id: string;
    name: string;
    nodes: Node[];
    edges: Edge[];
    updatedAt: string;
  }[];
  loadNodeDefinitions: () => Promise<void>;
  addNode: (nodeDefinition: WorkflowNodeDefinition, position: { x: number; y: number }) => void;
  updateNodeSettings: (nodeId: string, settings: Record<string, any>) => void;
  updateNodeInput: (nodeId: string, settings: Record<string, any>) => void;
  updateEdgeSettings: (edgeId: string, settings: Record<string, any>) => void;
  setSelectedNode: (nodeId: string | null) => void;
  setSelectedEdge: (edgeId: string | null) => void;
  setUserInput: (input: string) => void;
  setCurrentExecutionSavedId: (id: string) => void
  onNodesChange: (changes: any[]) => void;
  onEdgesChange: (changes: any[]) => void;
  onConnect: (connection: any) => void;
  executeWorkflow: () => Promise<void>;
  executeSingleNode: (nodeId: string) => Promise<void>;
  pinNodeOutput: (nodeId: string, output: any) => void;
  toggleNodePin: (nodeId: string) => void;
  saveWorkflow: (name: string) => void;
  createWorkflow: (name: string) => string;
  loadWorkflow: (id: string) => void;
  deleteWorkflow: (id: string) => void;
  updateWorkflow: (id: string, name?: string) => void;
}

const mapBackendNodeToDefinition = (backendNode: any): NodeDefinition => {
  let mappedCategory: NodeCategory = 'utilities';
  const cat = (backendNode.category || '').toLowerCase();
  if (cat.includes('ai') || cat.includes('language') || cat.includes('llm') || cat.includes('data')) {
    mappedCategory = 'language-models';
  } else if (cat.includes('diffusion') || cat.includes('image') || cat.includes('generation')) {
    mappedCategory = 'diffusion-models';
  } else if (cat.includes('voice') || cat.includes('audio') || cat.includes('speech') || cat.includes('synthesis')) {
    mappedCategory = 'voice-synthesis';
  } else if (cat.includes('utility') || cat.includes('tool') || cat.includes('logic')) {
    mappedCategory = 'utilities';
  } else if (cat.includes('input') || cat.includes('output')) {
    mappedCategory = 'input-output';
  } else if (cat.includes('google') || cat.includes('workspace')) {
    mappedCategory = 'google-workspace';
  }

  const settings: NodeSetting[] = (backendNode.fields || []).map((f: any) => {
    let settingType: SettingType = 'text';
    const ft = (f.type || '').toLowerCase();
    if (ft === 'select') settingType = 'select';
    else if (ft === 'textarea') settingType = 'textarea';
    else if (ft === 'slider' || ft === 'range') settingType = 'range';
    else if (ft === 'number') settingType = 'number';
    else if (ft === 'boolean' || ft === 'switch') settingType = 'boolean';
    else if (ft === 'file') settingType = 'file';
    else if (ft === 'connection_select' || ft === 'credential' || ft === 'connection') {
      settingType = 'credential';
    }

    let rawOptions = f.options;
    if ((!rawOptions || rawOptions.length === 0) && f.name === 'model') {
      const typeLower = backendNode.type?.toLowerCase() || '';
      if (typeLower.includes('gemini') || typeLower.includes('google') || typeLower.includes('vertex')) {
        rawOptions = [
          "gemini-2.5-flash",
          "gemini-1.5-pro-002",
          "gemini-1.5-flash-002",
          "models/gemini-2.5-flash",
          "models/gemini-1.5-pro-002",
          "models/gemini-1.5-flash-002"
        ];
      }
    }

    return {
      id: f.name,
      name: f.label || f.name,
      type: settingType,
      description: f.description || '',
      default: f.default !== undefined ? f.default : '',
      options: rawOptions ? rawOptions.map((opt: any) => {
        if (typeof opt === 'string') {
          const label = opt
            .split('-')
            .map(word => {
              if (word === 'gemini') return 'Gemini';
              if (word === 'pro') return 'Pro';
              if (word === 'flash') return 'Flash';
              if (word === 'lite') return 'Lite';
              return word.charAt(0).toUpperCase() + word.slice(1);
            })
            .join(' ');
          return { label, value: opt };
        }
        return {
          label: opt.label || opt.name || opt.text || opt.id || '',
          value: opt.value || opt.id || opt.name || ''
        };
      }) : undefined,
      required: !!f.required,
      placeholder: f.placeholder || '',
      connection_type: f.name === 'connection_id' ? backendNode.type.replace('Node', '') : undefined,
    };
  });

  const inputs: NodePort[] = [
    { id: 'input', name: 'Input', type: 'any', required: false }
  ];

  const outputs: NodePort[] = (backendNode.outputs || ['output']).map((outName: string) => ({
    id: outName,
    name: outName.charAt(0).toUpperCase() + outName.slice(1),
    type: 'any',
    required: false
  }));

  return {
    id: backendNode.type,
    name: backendNode.display_name || backendNode.type,
    category: mappedCategory,
    description: backendNode.description || '',
    icon: backendNode.icon || 'Bot',
    inputs,
    outputs,
    settings,
  };
};

export const useWorkflowStore = create<WorkflowState>()(
  persist(
    (set, get) => ({
      nodes: [],
      edges: [],
      selectedNodeId: null,
      selectedEdgeId: null,
      isRunning: false,
      userInput: '',
      isCurrentExecutionSavedId: null,
      currentWorkflowName: null,
      currentExecution: null,
      savedWorkflows: [],
      nodeDefinitions: [],
      loadNodeDefinitions: async () => {
        try {
          const response = await getNodesRegistry();
          const nodes = response.data.nodes;
          if (nodes && Array.isArray(nodes)) {
            set({ nodeDefinitions: nodes });
          }
        } catch (error) {
          console.error("Error loading node definitions from backend registry:", error);
        }
      },
      createWorkflow: (name) => {
        const id = `workflow-${Date.now()}`;
        set(
          produce((state: WorkflowState) => {
            const newWorkflow = {
              id,
              name,
              nodes: [],
              edges: [],
              updatedAt: new Date().toISOString(),
            };
            state.savedWorkflows.push(newWorkflow);
          })
        );
        return id;
      },
      addNode: (nodeDefinition, position) => {
        set(
          produce((state: WorkflowState) => {
            // Check for position collision to avoid invisible stacked nodes
            let finalPosition = { ...position };
            let attempts = 0;
            while (attempts < 10) {
              const collision = state.nodes.some(
                (n) =>
                  Math.abs(n.position.x - finalPosition.x) < 10 &&
                  Math.abs(n.position.y - finalPosition.y) < 10
              );
              if (collision) {
                finalPosition.x += 30;
                finalPosition.y += 30;
                attempts++;
              } else {
                break;
              }
            }

            const newNode = {
              id: `${nodeDefinition.type}-${Date.now()}`,
              type: 'custom',
              position: finalPosition,
              data: nodeDefinition as unknown as Record<string, unknown>,
            };
            state.nodes.push(newNode);
          })
        );
      },
      setCurrentExecutionSavedId(id) {
        set({ isCurrentExecutionSavedId: id });
      },
      updateNodeInput: (nodeId: string, updatedInput: Record<string, any>) => {
        set((state) => {
          const updatedNodes = state.nodes.map((node) => {
            if (node.id !== nodeId) return node;

            // Create a deep copy of the node data
            const updatedData = JSON.parse(JSON.stringify(node.data));
            if (updatedData.inputs && updatedData.inputs.length > 0) {
              try {
                navigator.clipboard.writeText(JSON.stringify(updatedData.inputs[0]));
              } catch (e) { }
            }

            // Update the input field in the node data
            if (updatedData.inputs && Array.isArray(updatedData.inputs)) {
              Object.entries(updatedInput).forEach(([key, value]) => {
                // Find the matching setting in the array by id or name
                const settingIndex = updatedData.inputs.findIndex((setting: { id?: string, name?: string }) => setting.id === key || setting.name === key);

                // If found, update its value
                if (settingIndex !== -1) {
                  updatedData.inputs[settingIndex] = {
                    ...updatedData.inputs[settingIndex],
                    default: value
                  };
                }
              });
            }

            console.log('Updated node data:', updatedData);

            return {
              ...node,
              data: updatedData
            };
          });

          return { nodes: updatedNodes };
        })
      },
      updateNodeSettings: (nodeId: string, updatedSettings: Record<string, any>) => {
        console.log('Updating node settings:', nodeId, updatedSettings);

        set((state) => {
          const updatedNodes = state.nodes.map((node) => {
            if (node.id !== nodeId) return node;

            // Create a deep copy of the node data
            const updatedData = JSON.parse(JSON.stringify(node.data));

            // Update specific settings by their keys
            if (updatedData.settings && Array.isArray(updatedData.settings)) {
              // For each setting we want to update
              Object.entries(updatedSettings).forEach(([key, value]) => {
                // Find the matching setting in the array by id or name
                const settingIndex = updatedData.settings.findIndex((setting: { id?: string, name?: string }) => setting.id === key || setting.name === key);

                // If found, update its value
                if (settingIndex !== -1) {
                  updatedData.settings[settingIndex] = {
                    ...updatedData.settings[settingIndex],
                    default: value
                  };
                }
              });
            }

            // Also check fields array to support new payload structure
            if (updatedData.fields && Array.isArray(updatedData.fields)) {
              Object.entries(updatedSettings).forEach(([key, value]) => {
                // Find the matching field in the array by name or id
                const fieldIndex = updatedData.fields.findIndex((field: { name?: string, id?: string }) => field.name === key || field.id === key);

                // If found, update its value
                if (fieldIndex !== -1) {
                  updatedData.fields[fieldIndex] = {
                    ...updatedData.fields[fieldIndex],
                    default: value
                  };
                }
              });
            }

            // Also set it at top-level of data to be safe, as getSettingValue looks there first
            Object.entries(updatedSettings).forEach(([key, value]) => {
              updatedData[key] = value;
            });

            console.log('Updated node data:', updatedData);

            return {
              ...node,
              data: updatedData
            };
          });

          return { nodes: updatedNodes };
        });
      },

      updateEdgeSettings: (edgeId, settings) => {
        set(
          produce((state: WorkflowState) => {
            const edge = state.edges.find(e => e.id === edgeId);
            if (edge) {
              Object.assign(edge, settings);
            }
          })
        );
      },

      setSelectedNode: (nodeId) => {
        set({ selectedNodeId: nodeId });
        set({ selectedEdgeId: undefined });
      },
      setSelectedEdge: (edgeId) => {
        set({ selectedEdgeId: edgeId });
        set({ selectedNodeId: undefined });
      },

      setUserInput: (input) => {
        set({ userInput: input });
      },

      onNodesChange: (changes) => {
        set(
          produce((state: WorkflowState) => {
            changes.forEach(change => {
              if (change.type === 'remove') {
                state.nodes = state.nodes.filter(node => node.id !== change.id);
                state.edges = state.edges.filter(
                  edge => edge.source !== change.id && edge.target !== change.id
                );
              } else if (change.type === 'position' && change.position) {
                const node = state.nodes.find(n => n.id === change.id);
                if (node) {
                  node.position = change.position;
                }
              }
            });
          })
        );
      },

      onEdgesChange: (changes) => {
        set(
          produce((state: WorkflowState) => {
            changes.forEach(change => {
              if (change.type === 'remove') {
                state.edges = state.edges.filter(edge => edge.id !== change.id);
              }
            });
          })
        );
      },

      onConnect: (connection) => {
        set(
          produce((state: WorkflowState) => {
            // Prevent duplicate edges in store state
            const exists = state.edges.some(
              (edge) =>
                edge.source === connection.source &&
                edge.target === connection.target
            );
            if (exists) return;

            const newEdge = {
              id: `e${connection.source}-${connection.target}`,
              source: connection.source,
              target: connection.target,
              sourceHandle: connection.sourceHandle,
              targetHandle: connection.targetHandle,
              auto_map: true,
              merge_strategy: 'concatenate',
              data_mappings: [],
              animated: false,
              label: '',
            };
            state.edges.push(newEdge);
          })
        );
      },

      executeWorkflow: async () => {
        const { userInput, isCurrentExecutionSavedId } = get();
        if (!isCurrentExecutionSavedId || isCurrentExecutionSavedId.startsWith('workflow-')) {
          showErrorToast("Please save your workflow before running.");
          return;
        }

        set({ isRunning: true });
        try {
          // Trigger the execution on the backend using runWorkflow API helper
          const response = await runWorkflow(isCurrentExecutionSavedId, {
            initial_input: { input: userInput },
            async_execution: true,
          });

          const executionId = response?.execution_id || response?.id || response?.data?.execution_id || response?.data?.id;
          if (!executionId) {
            throw new Error("No execution ID returned from backend.");
          }

          // Initialize local tracking structure for streaming
          const mockExecution: WorkflowExecution = {
            id: executionId,
            status: 'running',
            startTime: new Date(),
            nodes: {}
          };
          set({ currentExecution: mockExecution });

          // Establish EventSource (SSE) stream for real-time telemetry
          // We use a relative path so Next.js's built-in rewriting proxy maps it to 127.0.0.1:8000, preventing CORS errors natively.
          // We append token and access_token query parameters since EventSource does not support custom headers for authentication.
          const token = localStorage.getItem('upgrade-token') || '';
          const eventSource = new EventSource(`/api/v1/streams?token=${token}&access_token=${token}&channel=exec_trace:${executionId}`);

          eventSource.onmessage = (event) => {
            try {
              const data = JSON.parse(event.data);
              console.log("DEBUG: Telemetry event received from backend:", data);

              set((state) => {
                const nextExecution = state.currentExecution ? { ...state.currentExecution } : null;
                if (!nextExecution) return state;

                // Backend telemetry payload handles node state updates:
                // e.g., data = { type: 'node_start', node_id: 'node-1' }
                // or data = { type: 'node_end', node_id: 'node-1', status: 'completed', output: ... }
                // or data = { type: 'workflow_end', status: 'completed' }

                const isNodeStart = data.type === 'node_start' || (data.status === 'RUNNING' && data.node_id);
                const isNodeEnd = data.type === 'node_end' || ((data.status === 'SUCCESS' || data.status === 'FAILED') && data.node_id);
                const isWorkflowEnd = data.type === 'workflow_end';

                if (isNodeStart) {
                  nextExecution.nodes[data.node_id] = {
                    id: data.node_id,
                    status: 'running',
                    input: data.input || {}
                  };
                } else if (isNodeEnd) {
                  const nodeStatus = data.status === 'SUCCESS' || data.status === 'COMPLETED' ? 'completed' : 'error';
                  if (nextExecution.nodes[data.node_id]) {
                    nextExecution.nodes[data.node_id].status = nodeStatus;
                    nextExecution.nodes[data.node_id].output = data.output;
                    nextExecution.nodes[data.node_id].error = data.error;
                  } else {
                    nextExecution.nodes[data.node_id] = {
                      id: data.node_id,
                      status: nodeStatus,
                      output: data.output,
                      error: data.error,
                      input: {}
                    };
                  }
                } else if (isWorkflowEnd) {
                  nextExecution.status = data.status || 'completed';
                  nextExecution.endTime = new Date();
                  eventSource.close();
                  setTimeout(() => {
                    showSuccessToast(`Workflow execution ${data.status}!`);
                  }, 0);
                  return { currentExecution: nextExecution, isRunning: false };
                }

                return { currentExecution: nextExecution };
              });
            } catch (err) {
              console.error("Error parsing streaming telemetry event data:", err);
            }
          };

          eventSource.onerror = (err) => {
            console.error("EventSource failed:", err);
            // isRunning handled by poll
            eventSource.close();
            showErrorToast("Lost telemetry stream connection.");
          };

          // Polling fallback for executeWorkflow (SSE may be buffered by Next.js proxy)
          const pollInterval = setInterval(async () => {
            try {
              const res = await fetch(`/api/v1/executions/${executionId}/status`, { credentials: 'include', headers: { 'Authorization': `Bearer ${token}` } });
              if (!res.ok) return;
              const statusData = await res.json();
              const execStatus = statusData?.data?.status || statusData?.status;
              console.log("POLL [workflow]: execution status =", execStatus);
              if (execStatus === 'COMPLETED' || execStatus === 'FAILED') {
                clearInterval(pollInterval);
                eventSource.close();
                const detailRes = await fetch(`/api/v1/executions/${executionId}/timeline`, { credentials: 'include', headers: { 'Authorization': `Bearer ${token}` } });
                const detailData = detailRes.ok ? await detailRes.json() : null;
                const traces = detailData?.data?.traces || detailData?.traces || [];
                set((state) => {
                  const next = state.currentExecution ? { ...state.currentExecution, nodes: { ...(state.currentExecution.nodes || {}) } } : null;
                  if (!next) return { isRunning: false };
                  for (const t of traces) {
                    if (t.node_id) {
                      next.nodes[t.node_id] = {
                        id: t.node_id,
                        status: (t.status === 'SUCCESS' || t.status === 'COMPLETED') ? 'completed' : 'error',
                        output: t.outputs || t.output,
                        error: t.error_message,
                        input: t.inputs || {}
                      };
                    }
                  }
                  next.status = execStatus === 'COMPLETED' ? 'completed' : 'error';
                  next.endTime = new Date();
                  return { currentExecution: next, isRunning: false };
                });
                if (execStatus === 'COMPLETED') showSuccessToast("Workflow execution completed!");
                else showErrorToast("Workflow execution failed.");
              }
            } catch (e) { console.warn("Poll error:", e); }
          }, 2000);
          setTimeout(() => clearInterval(pollInterval), 300000);


        } catch (error) {
          set({ isRunning: false });
          showErrorToast("Failed to start workflow execution.");
          console.error('Workflow execution failed:', error);
        }
      },

      executeSingleNode: async (nodeId: string) => {
        const { isCurrentExecutionSavedId, userInput } = get();
        if (!isCurrentExecutionSavedId || isCurrentExecutionSavedId.startsWith('workflow-')) {
          showErrorToast("Please save your workflow before running.");
          return;
        }

        set({ isRunning: true });
        try {
          const response = await runWorkflow(isCurrentExecutionSavedId, {
            initial_input: { input: userInput },
            async_execution: true,
            single_node_id: nodeId
          });

          const executionId = response?.execution_id || response?.id || response?.data?.execution_id || response?.data?.id;
          if (!executionId) {
            throw new Error("No execution ID returned from backend.");
          }

          const mockExecution: WorkflowExecution = {
            id: executionId,
            status: 'running',
            startTime: new Date(),
            nodes: {
              [nodeId]: {
                id: nodeId,
                status: 'running',
                input: { input: userInput }
              }
            }
          };

          set({ currentExecution: mockExecution });
          showSuccessToast("Isolated node run started!");

          // Subscribe to telemetry stream
          const token = localStorage.getItem('upgrade-token') || '';
          const eventSource = new EventSource(`/api/v1/streams?token=${token}&access_token=${token}&channel=exec_trace:${executionId}`);

          eventSource.onmessage = (event) => {
            try {
              const data = JSON.parse(event.data);
              console.log("DEBUG: Telemetry event received from backend:", data);

              set((state) => {
                const nextExecution = state.currentExecution ? { ...state.currentExecution } : null;
                if (!nextExecution) return state;

                const isNodeStart = data.type === 'node_start' || (data.status === 'RUNNING' && data.node_id);
                const isNodeEnd = data.type === 'node_end' || ((data.status === 'SUCCESS' || data.status === 'FAILED' || data.status === 'COMPLETED') && data.node_id);
                const isWorkflowEnd = data.type === 'workflow_end';

                if (isNodeStart) {
                  nextExecution.nodes[data.node_id] = {
                    id: data.node_id,
                    status: 'running',
                    input: data.input || {}
                  };
                } else if (isNodeEnd) {
                  const nodeStatus = data.status === 'SUCCESS' || data.status === 'COMPLETED' ? 'completed' : 'error';
                  if (nextExecution.nodes[data.node_id]) {
                    nextExecution.nodes[data.node_id].status = nodeStatus;
                    nextExecution.nodes[data.node_id].output = data.output;
                    nextExecution.nodes[data.node_id].error = data.error;
                  } else {
                    nextExecution.nodes[data.node_id] = {
                      id: data.node_id,
                      status: nodeStatus,
                      output: data.output,
                      error: data.error,
                      input: {}
                    };
                  }
                } else if (isWorkflowEnd) {
                  nextExecution.status = data.status || 'completed';
                  nextExecution.endTime = new Date();
                  eventSource.close();
                  setTimeout(() => {
                    showSuccessToast(`Node execution completed!`);
                  }, 0);
                  return { currentExecution: nextExecution, isRunning: false };
                }

                return { currentExecution: nextExecution };
              });
            } catch (err) {
              console.error("Error parsing trace message:", err);
            }
          };

          eventSource.onerror = (err) => {
            console.error("EventSource failed:", err);
            set({ isRunning: false });
            eventSource.close();
          };

          // Polling fallback for buffered SSE
          const pollInterval = setInterval(async () => {
            try {
              const res = await fetch(`/api/v1/executions/${executionId}/status`, { credentials: 'include', headers: { 'Authorization': `Bearer ${token}` } });
              if (!res.ok) return;
              const statusData = await res.json();
              const execStatus = statusData?.data?.status || statusData?.status;
              console.log("POLL: execution status =", execStatus);
              if (execStatus === 'COMPLETED' || execStatus === 'FAILED') {
                clearInterval(pollInterval);
                eventSource.close();
                const detailRes = await fetch(`/api/v1/executions/${executionId}/timeline`, { credentials: 'include', headers: { 'Authorization': `Bearer ${token}` } });
                const detailData = detailRes.ok ? await detailRes.json() : null;
                const traces = detailData?.data?.traces || detailData?.traces || [];
                set((state) => {
                  const next = state.currentExecution ? { ...state.currentExecution, nodes: { ...(state.currentExecution.nodes || {}) } } : null;
                  if (!next) return { isRunning: false };
                  for (const t of traces) {
                    if (t.node_id) {
                      next.nodes[t.node_id] = {
                        id: t.node_id,
                        status: (t.status === 'SUCCESS' || t.status === 'COMPLETED') ? 'completed' : 'error',
                        output: t.outputs || t.output,
                        error: t.error_message,
                        input: t.inputs || {}
                      };
                    }
                  }
                  next.status = execStatus === 'COMPLETED' ? 'completed' : 'error';
                  next.endTime = new Date();
                  return { currentExecution: next, isRunning: false };
                });
                if (execStatus === 'COMPLETED') showSuccessToast("Node execution completed!");
              }
            } catch (e) { console.warn("Poll error:", e); }
          }, 2000);
          setTimeout(() => clearInterval(pollInterval), 300000);


        } catch (error) {
          set({ isRunning: false });
          showErrorToast("Failed to run node.");
          console.error("Error executing single node:", error);
        }
      },

      pinNodeOutput: (nodeId, output) => {
        set((state) => {
          const updatedNodes = state.nodes.map((node) => {
            if (node.id !== nodeId) return node;
            const updatedData = {
              ...node.data,
              pinned_output: output,
              use_pinned: true
            };
            return { ...node, data: updatedData };
          });
          return { nodes: updatedNodes };
        });
        showSuccessToast("Output pinned! Future workflow runs will use this output.");
      },

      toggleNodePin: (nodeId) => {
        set((state) => {
          const updatedNodes = state.nodes.map((node) => {
            if (node.id !== nodeId) return node;
            const usePinnedCurrent = (node.data as any).use_pinned || false;
            const updatedData = {
              ...node.data,
              use_pinned: !usePinnedCurrent
            };
            return { ...node, data: updatedData };
          });
          return { nodes: updatedNodes };
        });
      },

      saveWorkflow: async (name: string) => {
        const id = `workflow-${Date.now()}`
        const { nodes, edges } = get();
        try {
          const response = await axiosInstance.post(`/api/v1/workflows/`, {
            id: id,
            name: name,
            description: "Generated workflow",
            graph_definition: {
              nodes: nodes.map((n: any) => ({
                id: n.id,
                type: n.type || 'custom',
                position: n.position,
                data: n.data,
              })),
              edges: edges.map((e: any) => ({
                id: e.id,
                source: e.source,
                target: e.target,
                sourceHandle: e.sourceHandle || 'output',
                targetHandle: e.targetHandle || 'input',
                data_mappings: e.data_mappings || [],
                merge_strategy: e.merge_strategy || 'concatenate',
                auto_map: e.auto_map !== undefined ? e.auto_map : true,
                label: e.label || '',
                animated: e.animated || false,
              })),
              viewport: { x: 0, y: 0, zoom: 1 }
            },
            user_id: JSON.parse(localStorage.getItem("user") || '{"_id":""}')
              ._id,
          },
            {
              headers: {
                'Content-Type': 'application/json',
              }
            })
          showSuccessToast('Workflow saved successfully');
          console.log('Workflow saved:', response.data);
          const savedId = response.data?.id || response.data?.data?.id || id;
          set({ isCurrentExecutionSavedId: savedId, currentWorkflowName: name });
          if (typeof window !== 'undefined' && savedId && !window.location.href.includes(savedId)) {
              window.history.pushState({}, '', `/workflow/app/${savedId}`);
          }
        } catch (error) {
          showErrorToast('Error saving workflow');
          console.error('Error saving workflow:', error);
        }
      },
      updateWorkflow: async (id, name) => {
        const { nodes, edges, currentWorkflowName } = get();
        const activeName = name || currentWorkflowName || "Updated workflow";
        try {
          const response = await axiosInstance.put(`/api/v1/workflows/${id}`, {
            name: activeName,
            description: "Updated workflow",
            graph_definition: {
              nodes: nodes.map((n: any) => ({
                id: n.id,
                type: n.type || 'custom',
                position: n.position,
                data: n.data,
              })),
              edges: edges.map((e: any) => ({
                id: e.id,
                source: e.source,
                target: e.target,
                sourceHandle: e.sourceHandle || 'output',
                targetHandle: e.targetHandle || 'input',
                data_mappings: e.data_mappings || [],
                merge_strategy: e.merge_strategy || 'concatenate',
                auto_map: e.auto_map !== undefined ? e.auto_map : true,
                label: e.label || '',
                animated: e.animated || false,
              })),
              viewport: { x: 0, y: 0, zoom: 1 }
            },
            user_id: JSON.parse(localStorage.getItem("user") || '{"_id":""}')
              ._id,
          },
            {
              headers: {
                'Content-Type': 'application/json',
              }
            })
          showSuccessToast('Workflow updated successfully');
          console.log('Workflow updated:', response.data);
          set({ currentWorkflowName: activeName });
        } catch (error) {
          showErrorToast('Error updating workflow');
          console.error('Error updating workflow:', error);
        }
      },

      loadWorkflow: async (id: string) => {
        try {
          const response = await axiosInstance.get(`/api/v1/workflows/${id}`);
          const workflow = response.data?.data || response.data?.workflow || response.data;
          if (workflow) {
            const rawNodes = workflow.graph_definition?.nodes || workflow.nodes || [];
            const rawEdges = workflow.graph_definition?.edges || workflow.edges || [];

            // Dynamically remap legacy edge targetHandles from 'input' to 'prompt' if the target node requires 'prompt'
            const mappedEdges = rawEdges.map((edge: any) => {
              const targetNode = rawNodes.find((n: any) => n.id === edge.target);
              if (targetNode) {
                const nodeData = targetNode.data as any;
                const hasPromptField = Array.isArray(nodeData?.fields) && 
                  nodeData.fields.some((f: any) => f.name === 'prompt');
                
                if (hasPromptField && edge.targetHandle === 'input') {
                  return { ...edge, targetHandle: 'prompt' };
                }
              }
              return edge;
            });

            set({
              isCurrentExecutionSavedId: workflow.id || workflow._id,
              currentWorkflowName: workflow.name || "Untitled Workflow",
              nodes: rawNodes,
              edges: mappedEdges
            });
            console.log('Workflow loaded with remapped edges:', workflow);
          }
        } catch (error) {
          console.error('Error loading workflow:', error);
        }
      },

      deleteWorkflow: (id: string) => {
        set(
          produce((state: WorkflowState) => {
            state.savedWorkflows = state.savedWorkflows.filter(w => w.id !== id);
          })
        );
      },
    }),
    {
      name: 'workflow-storage',
      partialize: (state) => ({
        savedWorkflows: state.savedWorkflows,
        isCurrentExecutionSavedId: state.isCurrentExecutionSavedId,
        currentWorkflowName: state.currentWorkflowName,
        nodes: state.nodes,
        edges: state.edges,
      }),
    }
  )
);