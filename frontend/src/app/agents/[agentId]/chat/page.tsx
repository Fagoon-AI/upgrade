"use client"
import { API_ENDPOINTS } from '@/utils/api/api';
import axios from '@/lib/api/axios';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import React, { useEffect } from 'react'

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { IAgentView } from '@/types/agent';
import { Loader2 } from 'lucide-react';
import { showErrorToast } from '@/utils/toast';

const AgentChatHistoryCreationPage = () => {
    const params = useParams();
    const router = useRouter();
    const searchParams = useSearchParams();
    const queryClient = useQueryClient();
    
    // Get userId from URL param first
    const searchParamUserId = searchParams.get('userId');
    
    // Try cached agents list
    const cachedAgents = queryClient.getQueryData<IAgentView[]>(['agents', 'all']);
    const agentFromCache = cachedAgents?.find(
        (a: any) => a.id === params.agentId || a._id === params.agentId
    );
    const cachedUserId = searchParamUserId || (agentFromCache as any)?.user_id;

    // Fallback: fetch agent details to get user_id
    const { data: agentDetails, isLoading: isAgentLoading } = useQuery({
        queryKey: ['agent-details', params.agentId],
        queryFn: async () => {
            const response = await axios.get(`${API_ENDPOINTS.AGENT}/agent`);
            const agents = response.data?.data?.agents || response.data?.agents || [];
            return agents.find((a: any) => a.id === params.agentId || a._id === params.agentId);
        },
        enabled: !cachedUserId,
        staleTime: 1000 * 60 * 10,
    });

    const userId = cachedUserId || agentDetails?.user_id;
    
    const [isLoading, setIsLoading] = React.useState(true);
    const [error, setError] = React.useState<string | null>(null);

    const createNewChat = async () => {
        if (typeof window !== "undefined") {
            try {
                const response = await axios.post(
                    `${API_ENDPOINTS.AGENT}/agent/chat`,
                    {
                        user_id: userId || "", 
                        agent_id: params.agentId
                    },
                );

                const chatUuid = response.data.data.conversation_id;

                // Invalidate conversations list so it shows up in sidebar immediately
                queryClient.invalidateQueries({ queryKey: ["agent-conversations", params.agentId] });

                router.push(`/agents/${params.agentId}/chat/${chatUuid}?userId=${userId}`);

            } catch (err: any) {
                console.error("Error creating new chat:", err);
                setError(err?.response?.data?.message || "Failed to initialize agent chat. The backend route might be missing.");
                showErrorToast("Error initializing agent chat");
            } finally {
                setIsLoading(false);
            }
        }
    };

    useEffect(() => {
        if (!isAgentLoading && userId) {
            createNewChat();
        }
    }, [userId, isAgentLoading]);

    return (
        <div className="flex h-screen w-full items-center justify-center flex-col gap-4">
            {isLoading ? (
                <>
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    <p className="text-muted-foreground">Initializing agent chat session...</p>
                </>
            ) : error ? (
                <>
                    <div className="text-red-500 font-medium">Error</div>
                    <p className="text-muted-foreground">{error}</p>
                    <button 
                        onClick={() => router.push('/agents')}
                        className="px-4 py-2 bg-primary text-white rounded-md mt-4"
                    >
                        Go Back
                    </button>
                </>
            ) : null}
        </div>
    )
}

export default AgentChatHistoryCreationPage