import { Badge } from '@/components/ui/badge'
import { Calendar } from '@/components/ui/calendar'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { API_ENDPOINTS } from '@/utils/api/api'
import { HumanizeTimestamp } from '@/utils/data/date'
import axios from '@/lib/api/axios'
import Link from 'next/link'
import React, { useEffect, useState } from 'react'


interface IChatHistory {
    id: string;
    title: string;
    updated_at: string;
}

const AgentHistoryDialog = ({ agent_id }: { agent_id: string }) => {
    const [history, setHistory] = useState<IChatHistory[]>([])
    const [loading, setLoading] = useState<boolean>(true)
    useEffect(() => {
        const fetchHistory = async () => {
            const response = await axios.get(`${API_ENDPOINTS.AGENT}/agent/chat/${agent_id}/conversations`)
            setHistory(response.data.data.history || [])
            setLoading(false)
        }
        fetchHistory()
    }, [])
    if (loading) {
        return <>Loading...</>
    }
    return (
        <div className='flex flex-col gap-10'>
            <h2 className='text-2xl font-bold'>Agent History</h2>
            <div className="h-[50vh] px-6 pb-6 overflow-y-auto custom-scrollbar">
                <div className="flex flex-col gap-3">
                    {history.reverse().map((chat) => (
                        <Link
                            href={`/agents/${agent_id}/chat/${chat.id}`}
                            key={chat.id}
                            className='w-full'
                        >
                            <Card
                                className="cursor-pointer transition-all hover:shadow-md hover:border-blue-200 dark:hover:border-blue-700 group"
                            >
                                <CardContent className="p-4 flex justify-between">
                                    <div className="flex justify-between mb-2 flex-col">
                                        <div className="flex items-center justify-between mb-2">
                                            <h3 className="font-semibold text-base group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                                                {chat.title || 'Untitled Conversation'}
                                            </h3>
                                        </div>
                                        {HumanizeTimestamp(chat.updated_at)}
                                    </div>
                                    <div className="flex items-center justify-center text-muted-foreground group-hover:text-foreground">
                                        <Badge variant="secondary">View</Badge>
                                    </div>
                                </CardContent>
                            </Card>
                        </Link>
                    ))}
                </div>
            </div>
        </div>
    )
}

export default AgentHistoryDialog