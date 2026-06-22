/* eslint-disable @typescript-eslint/no-explicit-any */
import { Button } from '@/components/ui/button'
import { HumanizeTimestamp } from '@/utils/data/date';
import React, { useEffect, useState } from 'react'
import { WiTime2 } from "react-icons/wi";
import LoadingPage from '@/app/loading';
import { useRouter } from 'next/navigation';
import { Card, CardContent } from '@/components/ui/card';
import { Plus } from 'lucide-react';
import { useWorkflowStore } from '@/lib/store/workflow';
import { LuWorkflow } from 'react-icons/lu';
import { getWorkflows } from '@/lib/api/workflow';

const WorkflowDashboard = () => {
    const router = useRouter()
    const [workflows, setWorkflows] = useState<any[]>([])
    const [isLoading, setLoading] = useState(false)
    const { loadWorkflow } = useWorkflowStore()

    useEffect(() => {
        const fetchWorkflows = async () => {
            try {
                setLoading(true);
                const responseData = await getWorkflows();
                const workflowsList = responseData?.data || (responseData as any)?.workflows || (Array.isArray(responseData) ? responseData : []);
                
                // Map workflows to ensure they have the exact structure needed by the dashboard
                const mappedWorkflows = workflowsList.map((workflow: any) => ({
                    ...workflow,
                    id: workflow.id || workflow._id,
                    name: workflow.name || "Untitled Workflow",
                    nodes: workflow.graph_definition?.nodes || workflow.nodes || [],
                    edges: workflow.graph_definition?.edges || workflow.edges || [],
                    createdAt: workflow.created_at || workflow.createdAt || new Date().toISOString(),
                    updatedAt: workflow.updated_at || workflow.updatedAt || new Date().toISOString(),
                }));
                
                setWorkflows(mappedWorkflows);
                setLoading(false);
            } catch (error) {
                setLoading(false);
            }
        }
        fetchWorkflows()
    }, [])

    const createNewWorkflow = async () => {
        try {
            const { createWorkflow, setCurrentExecutionSavedId } = useWorkflowStore.getState();
            useWorkflowStore.setState({ nodes: [], edges: [] });
            const newFlowId = createWorkflow("Untitled Workflow");
            setCurrentExecutionSavedId(newFlowId);
            
            router.push(`/workflow/app`);
        } catch (e) {
            console.error("Error creating new workflow:", e);
        }
    }

    return (
        <div className='flex flex-col gap-7'>
            <div className='flex justify-between gap-5'>
                <div className="bg-white/40 flex-1 backdrop-blur-3xl border border-gray-100 dark:border-gray-700  dark:bg-[#2f2f2f] rounded-lg shadow-md p-6 flex flex-col justify-between">
                    <div className='w-full h-full flex flex-col gap-2 text-sm'>
                        Total Workflows
                        <div className='text-2xl font-extrabold'>{workflows.length || 0}</div>
                    </div>
                </div>
                <div className="bg-white/40 flex-1 backdrop-blur-3xl border border-gray-100 dark:border-gray-700  dark:bg-[#2f2f2f] rounded-lg shadow-md p-6 flex flex-col justify-between">
                    <div className='w-full h-full flex flex-col gap-2 text-sm'>
                        Published Workflows
                        <div className='text-2xl font-extrabold'>{workflows?.filter(i => i.published === true).length}</div>
                    </div>
                </div>
            </div>
            <div className='flex flex-col gap-4'>
                <div className='leading-none'>
                    Your Workflows
                    <p className='text-sm leading-none text-gray-300'>Quick overview of configured workflows</p>
                </div>
                {isLoading ? <LoadingPage /> :

                    <div className='flex gap-3 flex-wrap'>
                        {workflows.map((workflow: any) => (
                            <div key={workflow.id} className="bg-white/40 backdrop-blur-3xl border border-gray-100 dark:border-gray-700  dark:bg-[#2f2f2f] rounded-lg shadow-md flex 
                        flex-col justify-between w-full">
                                <div className='w-full h-full flex justify-between gap-2 text-sm p-2'>
                                    {workflow.name}
                                </div>
                                <div className='px-2 pb-2'>
                                    Nodes: {workflow.nodes.length}
                                </div>
                                <div className='flex items-center gap-2 text-gray-400 px-2 pb-2 text-sm'>
                                    <WiTime2 />
                                    Created: {HumanizeTimestamp(workflow.createdAt)}
                                </div>
                                <div className='flex flex-col items-center gap-2 px-2 pb-2'>
                                    <Button className='w-full' variant={'outline'}
                                        onClick={() => {
                                            console.log(workflow.id)
                                            loadWorkflow(workflow.id)
                                            router.push(`/workflow/app`)
                                        }}
                                    >< LuWorkflow />Load</Button>
                                </div>
                            </div>
                        ))}
                        <Card 
                            onClick={createNewWorkflow}
                            className="cursor-pointer flex flex-col items-center justify-center border-dashed w-full hover:bg-accent/20 transition-colors"
                        >
                            <CardContent className="flex flex-col items-center justify-center py-8 w-full">
                                <div className='flex flex-col items-center gap-2 w-full'>
                                    <div className="h-20 w-20 rounded-full border border-slate-200 dark:border-neutral-800 bg-background flex items-center justify-center shadow-sm hover:bg-accent transition-colors">
                                        <Plus className="h-10 w-10 text-slate-500 dark:text-neutral-400" />
                                    </div>
                                    <p className="mt-4 text-sm font-medium text-center">Create New Workflow</p>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                }

            </div>
        </div>
    )
}

export default WorkflowDashboard