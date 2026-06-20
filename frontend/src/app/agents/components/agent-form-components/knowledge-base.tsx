import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useFormContext } from 'react-hook-form'
import { AgentFormData } from '@/lib/schemas/agent'
import * as agentApi from '@/lib/api/agent'
import { FileText, Loader2, Trash2 } from 'lucide-react'
import React, { useRef, useState } from 'react'
import { showSuccessToast, showErrorToast } from "@/utils/toast"
import { useMe } from '@/lib/store/user'
import { useMutation } from '@tanstack/react-query'

const KnowledgeBaseForm = () => {
    const { setValue, watch, formState: { errors } } = useFormContext<AgentFormData>()
    const fileInputRef = useRef<HTMLInputElement>(null)
    const { data: user } = useMe()
    
    const [tempUrl, setTempUrl] = useState<string>('')
    const urls = watch('knowledge_base.urls') || []
    const filePaths = watch('knowledge_base.uploaded_files') || []

    const uploadMutation = useMutation({
        mutationFn: (formData: FormData) => agentApi.uploadAgentFile(formData),
        onSuccess: (res) => {
            const newFileUrl = res.data?.files?.[0]?.gcs_path || res.data?.path || res.data?.fileUrl
            if (newFileUrl && typeof newFileUrl === 'string') {
                setValue('knowledge_base.uploaded_files', [...filePaths, newFileUrl])
                showSuccessToast('File uploaded successfully')
            } else {
                console.error("Unexpected upload response structure:", res)
                showErrorToast('Failed to upload file: invalid response format')
            }
        },
        onError: (err) => {
            console.error("Upload error:", err)
            showErrorToast('Failed to upload file')
        }
    })

    const handleDivClick = () => {
        fileInputRef.current?.click()
    }

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return

        const formData = new FormData()
        formData.append("files", file)
        
        const userId = user?._id || user?.id || user?.uuid || user?.data?.user?.id || user?.data?.id || user?.data?._id || ""
        formData.append("user_id", userId)
        
        uploadMutation.mutate(formData)
    }

    const handleAddUrl = () => {
        if (!tempUrl) return
        if (urls.length >= 10) {
            showSuccessToast('You can only add 10 URLs')
            return
        }
        try {
            new URL(tempUrl)
            setValue('knowledge_base.urls', [...urls, tempUrl])
            setTempUrl('')
        } catch (_) {
            showSuccessToast('Must be a valid URL')
        }
    }

    const removeUrl = (index: number) => {
        const newUrls = urls.filter((_, i) => i !== index)
        setValue('knowledge_base.urls', newUrls)
    }

    const removeFile = (index: number) => {
        const newFiles = filePaths.filter((_, i) => i !== index)
        setValue('knowledge_base.uploaded_files', newFiles)
        showSuccessToast('File removed')
    }

    return (
        <div className="space-y-4">
            <h3 className="text-lg font-medium">Knowledge Base</h3>
            <p className="text-sm text-muted-foreground">
                Add documents, websites, or other sources of information for your agent.
            </p>
            
            <div 
                className="border rounded-lg p-8 text-center cursor-pointer hover:bg-muted/50 transition-colors"
                onClick={handleDivClick}
            >
                {uploadMutation.isPending ? (
                    <Loader2 className="mx-auto h-8 w-8 text-muted-foreground mb-2 animate-spin" />
                ) : (
                    <FileText className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
                )}
                <p className="text-sm font-medium mb-2">
                    {uploadMutation.isPending ? "Uploading..." : "Add knowledge sources"}
                </p>
                <p className="text-xs text-muted-foreground mb-4">
                    Upload files or add links to websites to create a knowledge base
                </p>
                <Button type="button" variant="outline" size="sm" disabled={uploadMutation.isPending}>
                    Upload File
                </Button>
            </div>

            {filePaths.length > 0 && (
                <div className="space-y-2">
                    <Label className="text-xs font-semibold">Uploaded Files</Label>
                    <div className="flex flex-col gap-2 max-h-[150px] overflow-y-auto pr-2">
                        {filePaths.map((path, index) => (
                            <div key={index} className="flex items-center justify-between p-2 bg-muted rounded-md group">
                                <span className="text-sm truncate max-w-[250px]">
                                    {typeof path === 'string' ? path.split('/').pop() : 'Unknown file'}
                                </span>
                                <Button 
                                    type="button" 
                                    variant="ghost" 
                                    size="icon" 
                                    className="h-8 w-8 text-muted-foreground hover:text-red-500"
                                    onClick={() => removeFile(index)}
                                >
                                    <Trash2 className="h-4 w-4" />
                                </Button>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <div className="space-y-4 pt-4 border-t">
                <div className="flex items-center gap-2">
                    <Input 
                        placeholder="https://example.com" 
                        value={tempUrl} 
                        onChange={e => setTempUrl(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                                e.preventDefault()
                                handleAddUrl()
                            }
                        }}
                    />
                    <Button type="button" variant="outline" size="sm" onClick={handleAddUrl}>
                        Add URL
                    </Button>
                </div>
                
                {urls.length > 0 && (
                    <div className="flex flex-col gap-2 max-h-[150px] overflow-y-auto pr-2">
                        {urls.map((url, index) => (
                            <div key={index} className="flex items-center justify-between p-2 bg-muted rounded-md group">
                                <span className="text-sm truncate max-w-[250px]">{url}</span>
                                <Button 
                                    type="button" 
                                    variant="ghost" 
                                    size="icon" 
                                    className="h-8 w-8 text-muted-foreground hover:text-red-500"
                                    onClick={() => removeUrl(index)}
                                >
                                    <Trash2 className="h-4 w-4" />
                                </Button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                onChange={handleFileChange}
            />
        </div>
    )
}

import { Label } from '@/components/ui/label'

export default KnowledgeBaseForm