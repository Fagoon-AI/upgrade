"use client";

import { useCallback, useEffect, useState } from 'react';
import {
    ReactFlow,
    Background,
    MiniMap,
    Edge,
    Node,
    Connection,
    NodeMouseHandler,
    OnNodesDelete,
    OnEdgesDelete,
    useReactFlow,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { NodeSidebar } from '@/components/sidebar/node-sidebar';
import { SettingsPanel } from '@/components/workflow/settings-panel';
import { EdgeSettingsPanel } from '@/components/workflow/edge-settings-panel';
import { ExecutionPanel } from '@/components/workflow/execution-panel';
import { SaveWorkflowDialog } from '@/components/workflow/save-workflow-dialog';
import { LoadWorkflowDialog } from '@/components/workflow/load-workflow-dialog';
import { CustomNode } from '@/components/workflow/custom-node';
import { useWorkflowStore } from '@/lib/store/workflow';
import { NODE_DEFINITIONS } from '@/lib/types/nodes/nodes';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Play, ZoomIn, ZoomOut, Maximize, Trash2 } from 'lucide-react';
import { TbWorldShare } from "react-icons/tb";
import { showSuccessToast, showErrorToast } from "@/utils/toast";
import axios from 'axios';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import WorkflowDashboard from '@/components/workflow/dashboard/workflow-dashboard';
import WorkflowExecutionLogs from '@/components/workflow/dashboard/execution-logs';
import { API_BASE_URL } from '@/utils/api/api';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { getNodesRegistry } from '@/lib/api/workflow';

// Node type definitions
const nodeTypes = {
    custom: CustomNode,
};

// Delete dialog state interface
interface DeleteDialogState {
    isOpen: boolean;
    itemType: 'node' | 'edge' | null;
    itemId: string | null;
}

/**
 * WorkflowPage Component
 * A professional workflow editor with node management, execution, and visualization
 */
export default function WorkflowPage() {

    const reactFlow = useReactFlow();


    // Access workflow store
    const {
        nodes,
        edges,
        selectedNodeId,
        selectedEdgeId,
        isRunning,
        userInput,
        isCurrentExecutionSavedId,
        onNodesChange,
        onEdgesChange,
        onConnect: storeOnConnect,
        addNode,
        setSelectedNode,
        setSelectedEdge,
        executeWorkflow,
        setUserInput,
        loadWorkflow,
        loadNodeDefinitions,
        nodeDefinitions
    } = useWorkflowStore();
    const params = useParams();
    const workflowId = params.workflowId as string;
    // Delete confirmation dialog state
    const [deleteDialog, setDeleteDialog] = useState<DeleteDialogState>({
        isOpen: false,
        itemType: null,
        itemId: null,
    });

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Delete') {
                if (selectedNodeId) {
                    handleDeleteSelected('node')
                }
                if (selectedEdgeId) {
                    handleDeleteSelected('edge')
                }
            }
        }

        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [])
    useEffect(() => {
        loadWorkflow(workflowId)
    }, [workflowId])

    useEffect(() => {
        // const loadWorkflowFromParams = async () => {
        loadWorkflow(workflowId)
        loadNodeDefinitions()
        // }
    }, [])

    // Reference to ReactFlow instance for viewport manipulation
    const [isPublishing, setIsPublishing] = useState(false);

    const [isWorkflowDashboardOpen, setIsWorkflowDashboardOpen] = useState(false);

    const handlePublish = async () => {
        if (isPublishing) return;
        if (nodes.length === 0) {
            showErrorToast("Cannot publish an empty workflow");
            return;
        }

        if (!isCurrentExecutionSavedId || isCurrentExecutionSavedId.startsWith('workflow-')) {
            showErrorToast("Please save the workflow before publishing");
            return;
        }
        setIsPublishing(true);
        try {
            const response = await axios.post(`${API_BASE_URL}/api/v1/workflow/publish`, {
                workflowId: isCurrentExecutionSavedId,
            }, {
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${localStorage.getItem('upgrade-token')}`,
                },
            });
            if (response.status === 200) {
                showSuccessToast("Workflow published successfully");
            } else {
                showErrorToast("Failed to publish workflow");
            }

        } catch (e) {
            console.error('Error publishing workflow:', e);
            showErrorToast("Failed to publish workflow");
        } finally {
            setIsPublishing(false);
        }
    }
    /**
     * Adds a new node to the workflow
     */
    const handleNodeAdd = useCallback((nodeId: string) => {
        const nodeDefinition = nodeDefinitions.find(def => def.type === nodeId);
        if (!nodeDefinition) return;

        addNode(nodeDefinition, { x: 100, y: 100 });
    }, [addNode, nodeDefinitions]);

    /**
     * Handles node selection
     */
    const handleNodeClick: NodeMouseHandler = useCallback((_, node) => {
        setSelectedNode(node.id);
    }, [setSelectedNode]);


    const handleEdgeClick = useCallback((event: React.MouseEvent, edge: Edge) => {
        event.stopPropagation();
        setSelectedEdge(edge.id);
    }, [setSelectedEdge]);
    /**
     * Handles edge connections between nodes
     */
    const handleConnect = useCallback(
        (connection: Connection) => {
            // Prevent self-connections
            if (connection.source === connection.target) {
                showErrorToast("Cannot connect a node to itself");
                return;
            }
            storeOnConnect(connection);
        },
        [storeOnConnect]
    );

    /**
     * Intercepts node deletion to show confirmation dialog
     */
    const handleNodesDelete: OnNodesDelete = useCallback((nodesToDelete: Node[]) => {
        if (nodesToDelete.length === 1) {
            setDeleteDialog({
                isOpen: true,
                itemType: 'node',
                itemId: nodesToDelete[0].id,
            });
            // Return false to prevent automatic deletion
            return false;
        }
        return true;
    }, []);

    /**
     * Intercepts edge deletion to show confirmation dialog
     */
    const handleEdgesDelete: OnEdgesDelete = useCallback((edgesToDelete: Edge[]) => {
        if (edgesToDelete.length === 1) {
            setDeleteDialog({
                isOpen: true,
                itemType: 'edge',
                itemId: edgesToDelete[0].id,
            });
            // Return false to prevent automatic deletion
            return false;
        }
        return true;
    }, []);

    /**
     * Handles request to delete currently selected node
     */
    const handleDeleteSelected = useCallback((itemType: 'edge' | 'node') => {
        if (selectedNodeId) {
            setDeleteDialog({
                isOpen: true,
                itemType: itemType,
                itemId: selectedNodeId,
            });
        }
        if (selectedEdgeId) {
            setDeleteDialog({
                isOpen: true,
                itemType: itemType,
                itemId: selectedEdgeId,
            });
        }
    }, [selectedNodeId, selectedEdgeId]);

    /**
     * Confirms deletion of node or edge
     */
    const handleConfirmDelete = useCallback(() => {
        if (!deleteDialog.itemId) return;

        if (deleteDialog.itemType === 'node') {
            onNodesChange([{ type: 'remove', id: deleteDialog.itemId }]);
            setSelectedNode(null);
        } else if (deleteDialog.itemType === 'edge') {
            onEdgesChange([{ type: 'remove', id: deleteDialog.itemId }]);
            setSelectedEdge(null)
        }

        setDeleteDialog({ isOpen: false, itemType: null, itemId: null });
    }, [deleteDialog.itemType, deleteDialog.itemId, onNodesChange, onEdgesChange, setSelectedNode, setSelectedEdge]);

    /**
     * Viewport control handlers
     */
    const handleZoomIn = () => reactFlow.zoomIn();
    

    const handleZoomOut = () => {
        reactFlow.zoomOut();
    };

    const handleFitView = () => {
        reactFlow.fitView();
    };

    /**
     * Handles workflow execution
     */
    const runWorkflow = () => {
        if (isRunning) return;

        if (nodes.length === 0) {
            showErrorToast("Cannot run an empty workflow");
            return;
        }

        executeWorkflow();
    };

    return (
        <div className="flex h-screen bg-gray-100 dark:bg-background">
            {/* Node palette sidebar */}
            <NodeSidebar onNodeSelect={handleNodeAdd} onOpenDashboard={() => setIsWorkflowDashboardOpen(true)} />

            {/* Main workflow area */}
            <div className="flex-1 relative">
                {/* Workflow controls */}
                <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 w-full max-w-[95%] md:max-w-max px-2">
                    <div className="flex flex-col lg:flex-row items-center gap-2 bg-background/80 backdrop-blur-sm p-3 rounded-xl border border-[#FB923C] shadow-md w-full">
                        <Input
                            placeholder="Enter workflow input..."
                            value={userInput}
                            onChange={(e) => setUserInput(e.target.value)}
                            className="w-full focus-visible:ring-[#FB923C] shrink-0"
                        />
                        <div className="flex flex-wrap items-center justify-center gap-2 w-full md:w-auto">
                            <LoadWorkflowDialog />
                            <SaveWorkflowDialog />
                            <Button
                                onClick={runWorkflow}
                                disabled={isRunning}
                                className="flex-1 md:flex-initial bg-[#FB923C] hover:bg-[#FB923C]/80 text-white shadow-sm h-9 px-3"
                            >
                                <Play className="h-4 w-4 mr-2" />
                                {isRunning ? "Running..." : <span>Run<span className="hidden md:inline"> Workflow</span></span>}
                            </Button>
                            <Button
                                onClick={handlePublish}
                                disabled={isPublishing}
                                className="flex-1 md:flex-initial bg-[#FB923C] hover:bg-[#FB923C]/80 text-white shadow-sm h-9 px-3"
                            >
                                <TbWorldShare className="h-4 w-4 mr-2" />
                                {isPublishing ? "Publishing..." : <span>Publish<span className="hidden md:inline"> Workflow</span></span>}
                            </Button>
                        </div>
                    </div>
                </div>

                {/* Delete selected edge button */}
                {selectedEdgeId && (
                    <div className="absolute top-20 right-4 z-10">
                        <div className="bg-background/90 backdrop-blur-sm p-2 rounded-lg border border-[#FB923C] shadow-md">
                            <Button
                                variant="destructive"
                                size="sm"
                                onClick={() => handleDeleteSelected('edge')}
                                className="bg-red-500 hover:bg-red-600"
                            >
                                <Trash2 className="h-4 w-4 mr-2" />
                                Delete Selected Edge
                            </Button>
                        </div>
                    </div>
                )}


                {/* ReactFlow canvas */}
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onConnect={handleConnect}
                    onEdgeClick={handleEdgeClick}
                    onNodeClick={handleNodeClick}
                    onNodesDelete={handleNodesDelete}
                    onEdgesDelete={handleEdgesDelete}
                    nodeTypes={nodeTypes}
                    //Enter custom edge logic here
                    fitView
                    // ref={flowRef}
                    proOptions={{ hideAttribution: true }}
                    className="touch-none"
                >
                    <Background color="#FB923C" gap={16} />
                    <MiniMap
                        nodeStrokeColor="#FB923C"
                        nodeColor="#ffffff"
                        nodeBorderRadius={2}
                        maskColor="rgba(251, 146, 60, 0.1)"
                    />

                    {/* Zoom controls */}
                    <div className="absolute z-10 bottom-4 left-4 bg-background/90 backdrop-blur-sm p-2 rounded-lg border border-[#FB923C] shadow-md">
                        <div className="flex items-center gap-2">
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={handleZoomIn}
                                className="hover:bg-[#FB923C]/20"
                                title="Zoom In"
                            >
                                <ZoomIn className="h-4 w-4" />
                            </Button>
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={handleZoomOut}
                                className="hover:bg-[#FB923C]/20"
                                title="Zoom Out"
                            >
                                <ZoomOut className="h-4 w-4" />
                            </Button>
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={handleFitView}
                                className="hover:bg-[#FB923C]/20"
                                title="Fit View"
                            >
                                <Maximize className="h-4 w-4" />
                            </Button>
                        </div>
                    </div>
                </ReactFlow>

                {/* Execution results panel */}
                <ExecutionPanel />
            </div>

            {/* Settings panel for selected node */}
            {selectedNodeId && <SettingsPanel />}

            {/* Settings panel for selected edge */}
            {selectedEdgeId && <EdgeSettingsPanel />}

            {/* Delete confirmation dialog */}
            <Dialog
                open={deleteDialog.isOpen}
                onOpenChange={(open: boolean) => {
                    if (!open) {
                        setDeleteDialog({ isOpen: false, itemType: null, itemId: null });
                    }
                }}
            >
                <DialogContent className="border-[#FB923C]">
                    <DialogHeader>
                        <DialogTitle>Confirm Deletion</DialogTitle>
                        <DialogDescription>
                            Are you sure you want to delete this {deleteDialog.itemType}? This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button
                            variant="outline"
                            onClick={() => setDeleteDialog({ isOpen: false, itemType: null, itemId: null })}
                            className="border-[#FB923C] hover:bg-[#FB923C]/20"
                        >
                            Cancel
                        </Button>
                        <Button
                            variant="destructive"
                            onClick={handleConfirmDelete}
                            className="bg-red-500 hover:bg-red-600"
                        >
                            Delete
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
            <Dialog open={isWorkflowDashboardOpen} onOpenChange={setIsWorkflowDashboardOpen}>
                <DialogContent className="sm:max-w-[900px] h-[80vh] p-0">
                    <DialogHeader className="p-6 pb-2">
                        <DialogTitle>Workflows Dashboard</DialogTitle>
                        <DialogDescription>Monitor and analyze your workflow executions</DialogDescription>
                    </DialogHeader>
                    <Tabs defaultValue="dashboard" className="w-full">
                        <div className="px-6">
                            <TabsList className="grid w-full grid-cols-2">
                                <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
                                <TabsTrigger value="logs">Execution Logs</TabsTrigger>
                            </TabsList>
                        </div>
                        <ScrollArea className="h-[calc(80vh-120px)] px-6 py-4">
                            <TabsContent value="dashboard" className="mt-0">
                                <WorkflowDashboard />
                            </TabsContent>
                            <TabsContent value="logs" className="mt-0">
                                <WorkflowExecutionLogs />
                            </TabsContent>
                        </ScrollArea>
                    </Tabs>
                </DialogContent>
            </Dialog>
        </div>
    );
}