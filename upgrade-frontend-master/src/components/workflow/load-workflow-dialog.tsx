"use client";

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useWorkflowStore } from '@/lib/store/workflow';
import { Trash2 } from 'lucide-react';
import { Edge, Node } from '@xyflow/react';
import { API_BASE_URL } from '@/utils/api/api';
import { getWorkflows } from '@/lib/api/workflow';

export function LoadWorkflowDialog() {
  const [open, setOpen] = useState(false);
  const { loadWorkflow, deleteWorkflow } = useWorkflowStore();
  const [savedWorkflows, setSavedWorkflows] = useState<{
    id: string;
    name: string;
    nodes: Node[];
    edges: Edge[];
    updatedAt: string;
  }[]>([]);

  useEffect(() => {
    const fetchSavedWorkflows = async () => {
      try {
        const responseData = await getWorkflows();
        const workflowsList = responseData?.data || (responseData as any)?.workflows || (Array.isArray(responseData) ? responseData : []);
        if (workflowsList) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const workflows = workflowsList.map((workflow: any) => ({
            id: workflow.id || workflow._id,
            name: workflow.name || "Untitled Workflow",
            nodes: workflow.graph_definition?.nodes || workflow.nodes || [],
            edges: workflow.graph_definition?.edges || workflow.edges || [],
            updatedAt: new Date(workflow.updated_at || workflow.updatedAt || Date.now()).toLocaleString(),
          }));
          setSavedWorkflows(workflows);
        }
      } catch (error) {
        console.error('Error fetching saved workflows:', error);
      }
    };
    fetchSavedWorkflows();
  }, [open]);

  const handleLoad = (id: string) => {
    loadWorkflow(id);
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">Load Workflow</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Load Workflow</DialogTitle>
        </DialogHeader>
        <ScrollArea className="h-[400px] pr-4">
          {savedWorkflows.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              No saved workflows
            </p>
          ) : (
            <div className="space-y-2">
              {savedWorkflows.map((workflow) => (
                <div
                  key={workflow.id}
                  className="flex items-center justify-between p-3 rounded-lg border hover:bg-accent"
                >
                  <div>
                    <h4 className="font-medium">{workflow.name}</h4>
                    <p className="text-sm text-muted-foreground">
                      {new Date(workflow.updatedAt).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => deleteWorkflow(workflow.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => handleLoad(workflow.id)}
                    >
                      Load
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}