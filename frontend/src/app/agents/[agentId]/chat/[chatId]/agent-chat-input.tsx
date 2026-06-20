import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Send } from 'lucide-react'
import React, { useState } from 'react'
import AgentHistoryDialog from './agent-history'
const maxLength = 3000
interface AgentChatInputProps {
    handleSubmit: (text: string) => void
    agent_id: string
}
const AgentChatInput: React.FC<AgentChatInputProps> = ({ handleSubmit, agent_id }) => {
    const [inputValue, setInputValue] = useState<string>('')

    const handleFormSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        if (inputValue.trim()) {
            handleSubmit(inputValue.trim())
            setInputValue('')
        }
    }
    return (
        <div className="w-full space-y-4">
            <form onSubmit={handleFormSubmit} className="relative">
                <div className="relative">
                    <Input
                        type="text"
                        placeholder="Summarize the latest"
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        maxLength={maxLength}
                        className="w-full pr-12 py-6 text-base rounded-xl border-2 focus:border-primary"
                    />
                    <Button
                        type="submit"
                        size="sm"
                        className="absolute right-2 top-1/2 transform -translate-y-1/2 h-8 w-8 p-0 rounded-lg"
                        disabled={!inputValue.trim()}
                    >
                        <Send className="h-4 w-4" />
                        <span className="sr-only">Send message</span>
                    </Button>
                </div>
                <div className="flex justify-end mt-2 items-center gap-10">
                </div>
            </form>
        </div>
    )
}

export default AgentChatInput