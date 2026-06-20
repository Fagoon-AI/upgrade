"use client";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import * as agentApi from "@/lib/api/agent"
import { Loader2, Trash2, Edit, ExternalLink, FileText, Eye, EyeOff, Copy, Check, Settings2, Sparkles, BookOpen, User } from "lucide-react"
import { useEffect, useState } from "react"
import { CreateAgentDialog } from "./create-agent"
import { showSuccessToast, showErrorToast } from "@/utils/toast"
import axios from "@/lib/api/axios"

function ApiKeyDisplay({ apiKey }: { apiKey?: string }) {
    const [isVisible, setIsVisible] = useState(false);
    const [isCopied, setIsCopied] = useState(false);

    if (!apiKey) return <span className="text-muted-foreground italic">Not provided</span>;

    const copyToClipboard = () => {
        navigator.clipboard.writeText(apiKey);
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000);
        showSuccessToast("API key copied");
    };

    return (
        <div className="flex items-start gap-2 justify-end w-full">
            <div 
                className="font-mono bg-background px-3 py-1.5 rounded border text-xs cursor-pointer hover:bg-muted transition-colors flex items-start justify-between flex-1 overflow-hidden"
                onClick={copyToClipboard}
                title="Click to copy"
            >
                <span className={`mr-2 ${isVisible ? 'break-all text-left' : 'truncate'}`}>{isVisible ? apiKey : '••••••••••••••••••••••••••••••••••••••••'}</span>
                {isCopied ? <Check className="w-3.5 h-3.5 text-green-500 shrink-0 mt-0.5" /> : <Copy className="w-3.5 h-3.5 text-muted-foreground shrink-0 mt-0.5" />}
            </div>
            <button 
                onClick={() => setIsVisible(!isVisible)} 
                className="text-muted-foreground hover:text-foreground transition-colors p-1.5 border rounded bg-background hover:bg-muted shrink-0"
                title={isVisible ? "Hide API Key" : "Show API Key"}
            >
                {isVisible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
        </div>
    );
}

function ExpandableText({ text }: { text?: string }) {
    const [isExpanded, setIsExpanded] = useState(false);
    if (!text) return <span className="text-muted-foreground italic">None</span>;
    
    const words = text.split(/\s+/);
    if (words.length <= 30) {
        return <span>{text}</span>;
    }

    return (
        <div>
            <span className="whitespace-pre-wrap">{isExpanded ? text : words.slice(0, 30).join(' ') + '...'}</span>
            <button 
                className="ml-2 text-blue-500 hover:underline text-sm font-medium" 
                onClick={() => setIsExpanded(!isExpanded)}
            >
                {isExpanded ? 'Read less' : 'Read more'}
            </button>
        </div>
    )
}

function FileLink({ file }: { file: string }) {
    const [url, setUrl] = useState<string>('');
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const fetchUrl = async () => {
            try {
                if (file.startsWith('http://') || file.startsWith('https://')) {
                    setUrl(file);
                    return;
                }
                const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || "";
                const finalUrl = baseUrl ? `${baseUrl.replace(/\/$/, '')}/${file.replace(/^\//, '')}` : `/${file.replace(/^\//, '')}`;
                setUrl(finalUrl);
            } catch (err) {
                console.error("Failed to get file URL", err);
                setUrl(file);
            } finally {
                setIsLoading(false);
            }
        }
        fetchUrl();
    }, [file]);

    if (isLoading) return <span className="text-sm text-muted-foreground animate-pulse flex items-center gap-2"><Loader2 className="w-3 h-3 animate-spin"/> Loading link...</span>;

    return (
        <a href={url} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline text-sm flex items-center gap-1.5 truncate max-w-full">
            <FileText className="w-3.5 h-3.5 shrink-0" />
            <span className="truncate">{file.split('/').pop() || file}</span>
        </a>
    )
}

export function AgentDetailsModal({ isOpen, onClose, agentId }: { isOpen: boolean, onClose: () => void, agentId: string }) {
    const queryClient = useQueryClient();
    const [isEditing, setIsEditing] = useState(false);
    
    const { data: agentDetailsResponse, isLoading } = useQuery({
        queryKey: ['agent', agentId],
        queryFn: () => agentApi.getAgentDetails(agentId),
        enabled: isOpen && !!agentId,
    });

    const agent = agentDetailsResponse?.data?.agent || agentDetailsResponse?.agent || agentDetailsResponse?.data || agentDetailsResponse;

    const deleteMutation = useMutation({
        mutationFn: () => agentApi.deleteAgent(agentId),
        onSuccess: () => {
            showSuccessToast("Agent deleted successfully");
            queryClient.invalidateQueries({ queryKey: ['agents'] });
            onClose();
        },
        onError: () => {
            showErrorToast("Failed to delete agent");
        }
    });

    if (isEditing && agent) {
        return (
            <CreateAgentDialog 
                isOpen={true} 
                onClose={() => setIsEditing(false)} 
                agentToEdit={agent} 
            />
        );
    }

    const description = agent?.description || agent?.profile?.description;
    const systemPrompt = agent?.system_prompt || agent?.instructions;
    const urls = agent?.knowledge_base?.urls || [];
    const files = agent?.knowledge_base?.uploaded_files || agent?.knowledge_base?.file || [];

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="sm:max-w-5xl max-h-[90vh] overflow-y-auto p-0 border-0 shadow-2xl bg-background">
                <div className="sticky top-0 z-10 bg-background/80 backdrop-blur-xl border-b px-6 py-4 flex items-center justify-between">
                    <DialogHeader className="p-0 space-y-0 text-left">
                        <DialogTitle className="text-xl font-bold flex items-center gap-2">
                            <User className="w-5 h-5 text-primary" />
                            Agent Overview
                        </DialogTitle>
                        <DialogDescription className="text-xs mt-1">
                            View and manage configuration for this agent.
                        </DialogDescription>
                    </DialogHeader>
                </div>

                {isLoading ? (
                    <div className="flex justify-center items-center p-12 min-h-[300px]">
                        <Loader2 className="animate-spin w-8 h-8 text-primary/50" />
                    </div>
                ) : agent ? (
                    <div className="p-6 space-y-8">
                        {/* Header Section */}
                        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-5 py-2 px-5 rounded-2xl bg-muted/40 border border-muted">
                            {agent.profile?.image || agent.image ? (
                                <img src={agent.profile?.image || agent.image} alt={agent.name} className="w-20 h-20 rounded-full object-cover shadow-sm shrink-0 border-2 border-background" />
                            ) : (
                                <div className="w-20 h-20 rounded-full bg-gradient-to-br from-primary/20 to-primary/10 border-2 border-background shadow-sm shrink-0 flex items-center justify-center">
                                    <User className="w-8 h-8 text-primary/50" />
                                </div>
                            )}
                            <div className="space-y-1.5 flex-1">
                                <h3 className="text-2xl font-bold tracking-tight">{agent.name || agent.profile?.agent_name}</h3>
                                <div className="text-sm text-muted-foreground leading-relaxed max-w-2xl">
                                    <ExpandableText text={description} />
                                </div>
                            </div>
                        </div>
                        
                        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
                            {/* Left Column (Main Config) */}
                            <div className="lg:col-span-2 space-y-8">
                                {/* System Prompt */}
                                <div className="space-y-3">
                                    <h4 className="text-sm font-semibold flex items-center gap-2 text-foreground">
                                        <Sparkles className="w-4 h-4 text-primary" />
                                        System Prompt
                                    </h4>
                                    <div className="bg-muted/30 border border-muted p-5 rounded-xl text-sm leading-relaxed text-muted-foreground shadow-sm">
                                        <ExpandableText text={systemPrompt} />
                                    </div>
                                </div>

                                {/* Knowledge Base */}
                                <div className="space-y-3">
                                    <h4 className="text-sm font-semibold flex items-center gap-2 text-foreground">
                                        <BookOpen className="w-4 h-4 text-primary" />
                                        Knowledge Base
                                    </h4>
                                    <div className="bg-muted/30 border border-muted rounded-xl p-5 shadow-sm">
                                        {(urls.length === 0 && files.length === 0) ? (
                                            <p className="text-sm text-muted-foreground italic py-2">No knowledge base available.</p>
                                        ) : (
                                            <div className="space-y-5">
                                                {urls.length > 0 && (
                                                    <div className="space-y-2.5">
                                                        <h5 className="text-[11px] font-semibold text-muted-foreground tracking-wider uppercase">URLs</h5>
                                                        <ul className="space-y-2">
                                                            {urls.map((url: string, i: number) => (
                                                                <li key={i} className="flex items-center gap-2 bg-background border rounded-lg px-3 py-2.5 text-sm hover:bg-muted/50 transition-colors shadow-sm">
                                                                    <ExternalLink className="w-4 h-4 text-blue-500 shrink-0" />
                                                                    <a href={url} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline truncate">
                                                                        {url}
                                                                    </a>
                                                                </li>
                                                            ))}
                                                        </ul>
                                                    </div>
                                                )}
                                                {files.length > 0 && (
                                                    <div className="space-y-2.5">
                                                        <h5 className="text-[11px] font-semibold text-muted-foreground tracking-wider uppercase">Documents</h5>
                                                        <ul className="grid grid-cols-1 gap-2">
                                                            {files.map((file: any, i: number) => {
                                                                const filePath = typeof file === 'string' ? file : file.url || file.path || file.name;
                                                                if (!filePath) return null;
                                                                return (
                                                                    <li key={i} className="bg-background border rounded-lg px-3 py-2.5 text-sm hover:bg-muted/50 transition-colors shadow-sm">
                                                                        <FileLink file={filePath} />
                                                                    </li>
                                                                );
                                                            })}
                                                        </ul>
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Right Column (Settings) */}
                            <div className="lg:col-span-2 space-y-4">
                                <div className="space-y-3">
                                    <h4 className="text-sm font-semibold flex items-center gap-2 text-foreground">
                                        <Settings2 className="w-4 h-4 text-primary" />
                                        Model Configuration
                                    </h4>
                                    {agent.model_settings ? (
                                        <div className="bg-muted/30 border border-muted p-5 rounded-xl text-sm shadow-sm flex flex-col gap-1">
                                            <div className="flex items-center justify-between py-2.5 border-b border-border/50 gap-4">
                                                <span className="text-muted-foreground text-xs font-semibold tracking-wider uppercase shrink-0">Provider</span>
                                                <span className="font-semibold capitalize text-foreground bg-primary/10 text-primary px-3 py-1.5 rounded-md text-[12px]">{agent.model_settings.provider || agent.model_settings.llm_model?.split('-')[0] || 'default'}</span>
                                            </div>
                                            <div className="flex items-center justify-between py-2.5 border-b border-border/50 gap-4">
                                                <span className="text-muted-foreground text-xs font-semibold tracking-wider uppercase shrink-0">Model Name</span>
                                                <span className="font-medium text-foreground break-all text-right">{agent.model_settings.llm_model || 'default'}</span>
                                            </div>
                                            <div className="flex items-center justify-between py-2.5 border-b border-border/50 gap-4">
                                                <span className="text-muted-foreground text-xs font-semibold tracking-wider uppercase shrink-0 mt-1.5 self-start">API Key</span>
                                                <div className="flex-1 w-full max-w-[80%]">
                                                    <ApiKeyDisplay apiKey={agent.model_settings.api_key} />
                                                </div>
                                            </div>
                                            <div className="flex items-center justify-between py-2.5 border-b border-border/50 gap-4">
                                                <span className="text-muted-foreground text-xs font-semibold tracking-wider uppercase shrink-0">Temperature</span>
                                                <span className="font-medium font-mono text-foreground ">{agent.model_settings.temperature ?? 'N/A'}</span>
                                            </div>
                                            <div className="flex items-center justify-between py-2.5 border-b border-border/50 gap-4">
                                                <span className="text-muted-foreground text-xs font-semibold tracking-wider uppercase shrink-0">Top P</span>
                                                <span className="font-medium font-mono text-foreground">{agent.model_settings.top_p ?? 'N/A'}</span>
                                            </div>
                                            <div className="flex items-center justify-between py-2.5 gap-4">
                                                <span className="text-muted-foreground text-xs font-semibold tracking-wider uppercase shrink-0">Max Tokens</span>
                                                <span className="font-medium font-mono text-foreground">{agent.model_settings.max_tokens || 'Default'}</span>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="bg-muted/30 border border-muted p-5 rounded-xl text-sm shadow-sm flex items-center justify-center min-h-[120px]">
                                            <p className="text-muted-foreground italic">No settings available.</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="p-12 text-center text-muted-foreground">Agent not found.</div>
                )}
                
                <div className="sticky bottom-0 z-10 bg-background/80 backdrop-blur-xl border-t px-6 py-4 flex justify-between items-center w-full">
                    <Button variant="destructive" size="sm" className="shadow-sm" onClick={() => {
                        if (confirm('Are you sure you want to delete this agent? This action cannot be undone.')) {
                            deleteMutation.mutate()
                        }
                    }} disabled={deleteMutation.isPending || !agent}>
                        {deleteMutation.isPending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Trash2 className="w-4 h-4 mr-2" />}
                        Delete Agent
                    </Button>
                    <div className="flex gap-3">
                        <Button variant="outline" size="sm" onClick={onClose}>Close</Button>
                        <Button size="sm" className="shadow-sm" onClick={() => setIsEditing(true)} disabled={!agent}>
                            <Edit className="w-4 h-4 mr-2" />
                            Edit Configuration
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}
