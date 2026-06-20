import { Label } from '@/components/ui/label'
import { AgentToolEnum } from '@/types/agent'
import React from 'react'
import { useFormContext } from 'react-hook-form'
import { AgentFormData } from '@/lib/schemas/agent'
import { Switch } from '@/components/ui/switch'

const ToolsForm = () => {
    const { watch, setValue } = useFormContext<AgentFormData>()
    const selectedTools = watch('tools') || []

    const toggleTool = (tool: string) => {
        if (selectedTools.includes(tool)) {
            setValue('tools', selectedTools.filter(t => t !== tool))
        } else {
            setValue('tools', [...selectedTools, tool])
        }
    }

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-lg font-medium">Tools</h3>
                <p className="text-sm text-muted-foreground">
                    Enable tools that your agent can use to perform tasks.
                </p>
            </div>
            
            <div className="space-y-4">
                <div className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/50 transition-colors">
                    <div className="space-y-0.5">
                        <Label htmlFor="web_search" className="text-base cursor-pointer">Web Search</Label>
                        <p className="text-xs text-muted-foreground">Allow agent to search the internet for real-time information.</p>
                    </div>
                    <Switch 
                        id="web_search" 
                        checked={selectedTools.includes(AgentToolEnum.web_search)} 
                        onCheckedChange={() => toggleTool(AgentToolEnum.web_search)}
                    />
                </div>

                <div className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/50 transition-colors">
                    <div className="space-y-0.5">
                        <Label htmlFor="research" className="text-base cursor-pointer">Research</Label>
                        <p className="text-xs text-muted-foreground">Enable advanced research capabilities for deep analysis.</p>
                    </div>
                    <Switch 
                        id="research" 
                        checked={selectedTools.includes(AgentToolEnum.research)} 
                        onCheckedChange={() => toggleTool(AgentToolEnum.research)}
                    />
                </div>
            </div>
        </div>
    )
}

export default ToolsForm