import { Textarea } from '@/components/coder/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useFormContext } from 'react-hook-form'
import { AgentFormData } from '@/lib/schemas/agent'
import * as agentApi from '@/lib/api/agent'
import { ImageIcon, Loader2 } from 'lucide-react'
import React, { useRef, useState } from 'react'
import { useMe } from '@/lib/store/user'
import { useMutation } from '@tanstack/react-query'

const BasicInformationForm = () => {
    const { register, setValue, watch, formState: { errors } } = useFormContext<AgentFormData>()
    const fileInputRef = useRef<HTMLInputElement>(null)
    const { data: user } = useMe()
    
    const imageUrl = watch('profile.image')
    const [fileName, setFileName] = useState<string>(imageUrl?.split('/').pop() || '')

    const uploadMutation = useMutation({
        mutationFn: (formData: FormData) => agentApi.uploadAgentFile(formData),
        onSuccess: (res) => {
            const fileUrl = res.data.files[0].path
            setFileName(res.data.files[0].filename)
            setValue('profile.image', fileUrl)
        },
        onError: (err) => {
            console.error("Upload error:", err)
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

    return (
        <div className="space-y-4">
            <div className="space-y-2">
                <Label htmlFor="image">Agent Image</Label>
                <div 
                    className="flex items-center gap-4 cursor-pointer"
                    onClick={handleDivClick}
                >
                    <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center overflow-hidden border">
                        {imageUrl ? (
                            <img src={imageUrl} alt="Agent" className="w-full h-full object-cover" />
                        ) : (
                            <ImageIcon className="h-6 w-6 text-muted-foreground" />
                        )}
                    </div>
                    <div className="flex flex-col gap-1">
                        {fileName ? (
                            <span className="text-sm font-medium">{fileName}</span>
                        ) : (
                            <Button type="button" variant="outline" size="sm" disabled={uploadMutation.isPending}>
                                {uploadMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Upload Image"}
                            </Button>
                        )}
                    </div>
                </div>
            </div>
            
            <div className="space-y-2">
                <Label htmlFor="name">Name</Label>
                <Input 
                    id="name" 
                    placeholder="Enter agent name" 
                    {...register('profile.agent_name')} 
                />
                {errors.profile?.agent_name && (
                    <p className="text-xs text-red-500">{errors.profile.agent_name.message}</p>
                )}
            </div>
            
            <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                    id="description"
                    placeholder="Eg: Your task is to create cartoonish videos"
                    className="min-h-[100px]"
                    {...register('profile.description')}
                    maxLength={200}
                    rows={3}
                />
                {errors.profile?.description && (
                    <p className="text-xs text-red-500">{errors.profile.description.message}</p>
                )}
            </div>
            
            <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                accept="image/*"
                onChange={handleFileChange}
            />
        </div>
    )
}

export default BasicInformationForm