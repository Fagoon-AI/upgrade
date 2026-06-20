"use client"

import { useState, useEffect } from "react"
import { Copy, CheckCircle2, Save, Loader2, MessageSquare } from "lucide-react"
import { FaTelegramPlane, FaWhatsapp, FaFacebookMessenger } from "react-icons/fa"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { getAgentWebhookConfig, setAgentChannelConfig } from "@/lib/api/agent"
import { showSuccessToast, showErrorToast } from "@/utils/toast"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { API_BASE_URL } from "@/utils/api/api"

// Import our new WhatsApp QR Components
import { WhatsAppMethodSelector } from "./whatsapp-method-selector"
import { WhatsAppDisclaimer } from "./whatsapp-disclaimer"
import { WhatsAppQRPanel } from "./whatsapp-qr-panel"

interface DeployAgentModalProps {
    isOpen: boolean
    onClose: () => void
    agentId: string
    agentName: string
}

export function DeployAgentModal({ isOpen, onClose, agentId, agentName }: DeployAgentModalProps) {
    const [activeTab, setActiveTab] = useState("whatsapp")
    const [copiedStates, setCopiedStates] = useState<{ [key: string]: boolean }>({})
    const queryClient = useQueryClient()

    // Form states
    const [whatsappConfig, setWhatsappConfig] = useState({ phone_number_id: "", app_secret: "", access_token: "" })
    const [messengerConfig, setMessengerConfig] = useState({ page_id: "", app_secret: "", page_access_token: "" })
    const [telegramConfig, setTelegramConfig] = useState({ bot_token: "" })

    // WhatsApp QR states
    const [whatsappMethod, setWhatsappMethod] = useState<'meta' | 'qr'>('meta')
    const [whatsappDisclaimerAccepted, setWhatsappDisclaimerAccepted] = useState(false)

    const { data: webhookConfig, isLoading: isLoadingWebhooks } = useQuery({
        queryKey: ['agent-webhook-config', agentId],
        queryFn: () => getAgentWebhookConfig(agentId),
        enabled: isOpen && !!agentId
    })

    const mutation = useMutation({
        mutationFn: (data: any) => setAgentChannelConfig(agentId, data),
        onSuccess: () => {
            showSuccessToast("Channel configuration saved successfully")
            queryClient.invalidateQueries({ queryKey: ['agent-webhook-config', agentId] })
        },
        onError: (error: any) => {
            const msg = error?.response?.data?.message || error?.response?.data?.error || "Failed to save configuration"
            showErrorToast(msg)
        }
    })

    const handleCopy = (text: string, key: string) => {
        navigator.clipboard.writeText(text)
        setCopiedStates(prev => ({ ...prev, [key]: true }))
        setTimeout(() => {
            setCopiedStates(prev => ({ ...prev, [key]: false }))
        }, 2000)
    }

    const handleSaveWhatsapp = () => {
        mutation.mutate({
            channel: "whatsapp",
            ...whatsappConfig
        })
    }

    const handleSaveMessenger = () => {
        mutation.mutate({
            channel: "messenger",
            ...messengerConfig
        })
    }

    const handleSaveTelegram = () => {
        mutation.mutate({
            channel: "telegram",
            ...telegramConfig
        })
    }

    const getWebhookUrl = (channel: string) => {
        return `${API_BASE_URL}/api/v1/webhook/${channel}/${agentId}`
    }

    const getVerifyToken = (channel: string) => {
        if (webhookConfig?.data && webhookConfig.data[channel]?.verify_token) {
            return webhookConfig.data[channel].verify_token
        }
        return `verify_${agentId}_${channel}`
    }

    const WebhookSection = ({ channel, label }: { channel: string, label: string }) => {
        const webhookUrl = getWebhookUrl(channel)
        const verifyToken = getVerifyToken(channel)
        
        return (
            <div className="space-y-4 mb-6 p-4 bg-muted/50 rounded-lg border">
                <h4 className="text-sm font-semibold flex items-center gap-2">
                    {label} Webhook Details
                </h4>
                <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">Webhook URL</Label>
                    <div className="flex gap-2">
                        <Input readOnly value={webhookUrl} className="font-mono text-xs bg-background" />
                        <Button
                            variant="secondary"
                            size="icon"
                            onClick={() => handleCopy(webhookUrl, `${channel}_url`)}
                            className="shrink-0"
                        >
                            {copiedStates[`${channel}_url`] ? <CheckCircle2 className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                        </Button>
                    </div>
                </div>
                {channel !== 'telegram' && (
                    <div className="space-y-2">
                        <Label className="text-xs text-muted-foreground">Verify Token</Label>
                        <div className="flex gap-2">
                            <Input readOnly value={verifyToken} className="font-mono text-xs bg-background" />
                            <Button
                                variant="secondary"
                                size="icon"
                                onClick={() => handleCopy(verifyToken, `${channel}_token`)}
                                className="shrink-0"
                            >
                                {copiedStates[`${channel}_token`] ? <CheckCircle2 className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                            </Button>
                        </div>
                    </div>
                )}
            </div>
        )
    }

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <MessageSquare className="h-5 w-5 text-primary" />
                        Deploy to Channels
                    </DialogTitle>
                    <DialogDescription>
                        Connect <strong>{agentName}</strong> to popular messaging platforms.
                    </DialogDescription>
                </DialogHeader>

                <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full mt-4">
                    <TabsList className="grid w-full grid-cols-3">
                        <TabsTrigger value="whatsapp" className="flex items-center gap-2">
                            <FaWhatsapp className="text-[#25D366]" /> WhatsApp
                        </TabsTrigger>
                        <TabsTrigger value="messenger" className="flex items-center gap-2">
                            <FaFacebookMessenger className="text-[#0084FF]" /> Messenger
                        </TabsTrigger>
                        <TabsTrigger value="telegram" className="flex items-center gap-2">
                            <FaTelegramPlane className="text-[#0088cc]" /> Telegram
                        </TabsTrigger>
                    </TabsList>

                    {/* WHATSAPP TAB */}
                    <TabsContent value="whatsapp" className="mt-4 space-y-4">
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <FaWhatsapp className="text-[#25D366]" /> WhatsApp Configuration
                                </CardTitle>
                                <CardDescription>
                                    Configure how your agent connects to WhatsApp.
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <WhatsAppMethodSelector 
                                    selectedMethod={whatsappMethod} 
                                    onChange={setWhatsappMethod} 
                                />

                                {whatsappMethod === 'meta' && (
                                    <div className="space-y-4 animate-in fade-in slide-in-from-top-2">
                                        <WebhookSection channel="whatsapp" label="WhatsApp" />
                                        
                                        <div className="space-y-3">
                                            <div className="space-y-1">
                                                <Label>Phone Number ID</Label>
                                                <Input 
                                                    placeholder="e.g. 104561234567890" 
                                                    value={whatsappConfig.phone_number_id}
                                                    onChange={e => setWhatsappConfig({...whatsappConfig, phone_number_id: e.target.value})}
                                                />
                                            </div>
                                            <div className="space-y-1">
                                                <Label>App Secret</Label>
                                                <Input 
                                                    type="password"
                                                    placeholder="From your Meta App Dashboard" 
                                                    value={whatsappConfig.app_secret}
                                                    onChange={e => setWhatsappConfig({...whatsappConfig, app_secret: e.target.value})}
                                                />
                                            </div>
                                            <div className="space-y-1">
                                                <Label>Permanent Access Token</Label>
                                                <Input 
                                                    type="password"
                                                    placeholder="EAAL..." 
                                                    value={whatsappConfig.access_token}
                                                    onChange={e => setWhatsappConfig({...whatsappConfig, access_token: e.target.value})}
                                                />
                                            </div>
                                        </div>
                                        <Button 
                                            className="w-full mt-4" 
                                            onClick={handleSaveWhatsapp}
                                            disabled={mutation.isPending}
                                        >
                                            {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
                                            Save WhatsApp Config
                                        </Button>
                                    </div>
                                )}

                                {whatsappMethod === 'qr' && (
                                    <div className="space-y-4 animate-in fade-in slide-in-from-top-2">
                                        {!whatsappDisclaimerAccepted ? (
                                            <WhatsAppDisclaimer onAccept={() => setWhatsappDisclaimerAccepted(true)} />
                                        ) : (
                                            <WhatsAppQRPanel agentId={agentId} />
                                        )}
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* MESSENGER TAB */}
                    <TabsContent value="messenger" className="mt-4 space-y-4">
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <FaFacebookMessenger className="text-[#0084FF]" /> Messenger Configuration
                                </CardTitle>
                                <CardDescription>
                                    Connect your Facebook Page to allow the agent to handle Messenger conversations.
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <WebhookSection channel="messenger" label="Messenger" />
                                
                                <div className="space-y-3">
                                    <div className="space-y-1">
                                        <Label>Page ID</Label>
                                        <Input 
                                            placeholder="e.g. 104561234567890" 
                                            value={messengerConfig.page_id}
                                            onChange={e => setMessengerConfig({...messengerConfig, page_id: e.target.value})}
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <Label>App Secret</Label>
                                        <Input 
                                            type="password"
                                            placeholder="From your Meta App Dashboard" 
                                            value={messengerConfig.app_secret}
                                            onChange={e => setMessengerConfig({...messengerConfig, app_secret: e.target.value})}
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <Label>Page Access Token</Label>
                                        <Input 
                                            type="password"
                                            placeholder="EAAL..." 
                                            value={messengerConfig.page_access_token}
                                            onChange={e => setMessengerConfig({...messengerConfig, page_access_token: e.target.value})}
                                        />
                                    </div>
                                </div>
                                <Button 
                                    className="w-full mt-4" 
                                    onClick={handleSaveMessenger}
                                    disabled={mutation.isPending}
                                >
                                    {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
                                    Save Messenger Config
                                </Button>
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* TELEGRAM TAB */}
                    <TabsContent value="telegram" className="mt-4 space-y-4">
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <FaTelegramPlane className="text-[#0088cc]" /> Telegram Configuration
                                </CardTitle>
                                <CardDescription>
                                    Connect a Telegram Bot created via BotFather.
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <WebhookSection channel="telegram" label="Telegram" />
                                
                                <div className="space-y-3">
                                    <div className="space-y-1">
                                        <Label>Bot Token</Label>
                                        <Input 
                                            type="password"
                                            placeholder="e.g. 123456789:ABCdefGHIjklmNOPQrsTUVwxyZ" 
                                            value={telegramConfig.bot_token}
                                            onChange={e => setTelegramConfig({...telegramConfig, bot_token: e.target.value})}
                                        />
                                    </div>
                                </div>
                                <Button 
                                    className="w-full mt-4" 
                                    onClick={handleSaveTelegram}
                                    disabled={mutation.isPending}
                                >
                                    {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
                                    Save Telegram Config
                                </Button>
                            </CardContent>
                        </Card>
                    </TabsContent>
                </Tabs>
            </DialogContent>
        </Dialog>
    )
}
