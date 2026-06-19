import { Textarea } from '@/components/ui/textarea'
import React from 'react'
import { useFormContext } from 'react-hook-form'
import { AgentFormData } from '@/lib/schemas/agent'
import { Label } from '@/components/ui/label'

const SystemPromptForm = () => {
    const { register, formState: { errors } } = useFormContext<AgentFormData>()
    
    return (
        <div className="space-y-4">
            <h3 className="text-lg font-medium">System Prompt</h3>
            <p className="text-sm text-muted-foreground">Define how your agent should behave and respond.</p>
            <div className="space-y-2">
                <Label htmlFor="system_prompt" className="sr-only">System Prompt</Label>
                <Textarea 
                    id="system_prompt"
                    placeholder="You are a helpful assistant..." 
                    className="min-h-[300px] resize-none" 
                    {...register('system_prompt')}
                />
                {errors.system_prompt && (
                    <p className="text-xs text-red-500 font-medium">{errors.system_prompt.message}</p>
                )}
            </div>
        </div>
    )
}

export default SystemPromptForm