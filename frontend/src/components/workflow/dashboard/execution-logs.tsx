import LoadingPage from '@/app/loading'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { IWorkflowHistoryItem } from '@/lib/types/workflow'
import * as workflowApi from "@/lib/api/workflow"
import { HumanizeTimestamp } from '@/utils/data/date'
import { CheckCircle, Clock, XCircle } from 'lucide-react'
import React, { useEffect, useState } from 'react'
import { showSuccessToast } from "@/utils/toast"
import { LuDownload } from 'react-icons/lu'
import { MdContentCopy } from "react-icons/md";
import { useQuery } from '@tanstack/react-query'

function getContentType(response: string): 'text' | 'image' | 'video' | 'audio' {
    try {
        const ext = response.split('.').pop()?.toLowerCase();
        if (!ext) return 'text';

        const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'webp'];
        const videoExts = ['mp4', 'webm', 'mov', 'avi'];
        const audioExts = ['mp3', 'wav', 'ogg', 'm4a'];
        if (imageExts.includes(ext)) return 'image';
        if (videoExts.includes(ext)) return 'video';
        if (audioExts.includes(ext)) return 'audio';
    } catch {
        // Not a valid URL
    }

    return 'text';
}

const renderStatusBadge = (status: string) => {
    switch (status) {
        case "success":
            return (
                <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200 flex items-center gap-1">
                    <CheckCircle className="h-3 w-3" />
                    Success
                </Badge>
            )
        case "failed":
            return (
                <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200 flex items-center gap-1">
                    <XCircle className="h-3 w-3" />
                    Failed
                </Badge>
            )
        case "pending":
            return (
                <Badge variant="outline" className="bg-orange-50 text-orange-700 border-orange-200 flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    Pending
                </Badge>
            )
        default:
            return <Badge variant="outline">{status}</Badge>
    }
}

const WorkflowExecutionLogs = () => {
    const [fileUrls, setFileUrls] = useState<Record<string, string>>({});

    const { data: workflows = [], isLoading } = useQuery({
        queryKey: ['workflowHistory'],
        queryFn: async () => {
            const u = localStorage.getItem('user');
            if (!u) return [];
            const user = JSON.parse(u);
            const response = await workflowApi.getWorkflowHistory(user._id);
            return response.workflowHistory as IWorkflowHistoryItem[];
        }
    });

    const getFileUrl = async (url: string): Promise<string> => {
        const signedUrlResponse = await workflowApi.getFileUrl(url)
        return signedUrlResponse.data;
    }

    function downloadFile(url: string, filename?: string) {
        const a = document.createElement('a');
        a.href = url;
        a.download = filename || url.split('/').pop() || 'download';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    useEffect(() => {
        const fetchUrls = async () => {
            if (workflows.length === 0) return;
            const newUrls: Record<string, string> = {};

            await Promise.all(
                workflows.map(async (node) => {
                    if (node.result && getContentType(node.result) !== 'text') {
                        try {
                            const url = await getFileUrl(node.result);
                            newUrls[node._id] = url;
                        } catch (e) {
                            console.error(`Failed to fetch file URL for ${node._id}`, e);
                        }
                    } else {
                        newUrls[node._id] = node.result
                    }
                })
            );

            setFileUrls(newUrls);
        };
        fetchUrls();
    }, [workflows]);

    if (isLoading) {
        return <LoadingPage />
    }

    if (workflows.length === 0) {
        return (
            <div className="flex items-center justify-center h-full">
                <p className="text-gray-500">No workflows found.</p>
            </div>
        )
    }

    return (
        <div className='flex flex-col gap-2'>
            WorkflowExecutionLogs:
            <div className="rounded-md border">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Workflow</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Time</TableHead>
                            <TableHead>Executed From</TableHead>
                            <TableHead>Result</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {workflows.map((execution) => (
                            <TableRow key={execution._id}>
                                <TableCell className="font-medium">{execution.workflow.name}</TableCell>
                                <TableCell>{renderStatusBadge(execution.status)}</TableCell>
                                <TableCell className='w-32'>{HumanizeTimestamp(execution.time)}</TableCell>
                                <TableCell>{execution.executedFrom}</TableCell>
                                <TableCell className='max-h-[110px] line-clamp-6 pb-[-5] max-w-[400px]'>
                                    {getContentType(execution.result) === 'text' ?
                                        <div className="relative group ">
                                            {fileUrls[execution._id]}
                                            <button onClick={
                                                () => {
                                                    navigator.clipboard.writeText(fileUrls[execution._id])
                                                    showSuccessToast('Copied to clipboard')
                                                }
                                            } className="absolute right-2 top-2 -translate-y-1/2 hidden group-hover:flex bg-white  items-center justify-center p-2 rounded-full text-black">
                                                <MdContentCopy />
                                            </button>
                                        </div> :
                                        fileUrls[execution._id] ?
                                            <div className='flex items-center justify-center '>
                                                <div className='cursor-pointer'
                                                    onClick={() => downloadFile(fileUrls[execution._id], execution.result.split('/').pop())}
                                                >
                                                    <LuDownload />
                                                </div>
                                            </div> : <div>
                                                Loading.. please refresh in a while
                                            </div>
                                    }
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>
        </div>
    )
}

export default WorkflowExecutionLogs