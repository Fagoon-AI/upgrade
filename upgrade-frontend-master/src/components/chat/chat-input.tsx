import { Badge } from '@/components/ui/badge';
import React, { useState, useEffect } from 'react'
import { LuBrain } from 'react-icons/lu';
import { TfiWorld } from 'react-icons/tfi';
import axios from 'axios';
import { useUpgradeChat } from '@/app/(chat1)/hooks/useUpgradeChat';
import ModelSelector from './modalSelector';
import { ChatArea } from './ChatArea';
import { useSelectedModelContext } from '@/contexts/SelectedModelContext';
import { useQuery } from '@tanstack/react-query';
import { getModels } from '@/lib/api/models';
const ChatInput = ({ history_id, handleSubmitInput }: { history_id: string, handleSubmitInput: (text: string) => void }) => {
    const [selectedFile, setSelectedFile] = useState<string | null>(null);
    const { assignmentMode,
        browserMode,
        inputText,
        internetSearchEnabled,
        isStreaming,
        setAssignmentMode,
        setBrowserMode,
        setInputText,
        setInternetSearchEnabled,
        stopResponse,
    }
        = useUpgradeChat()

    const { selectedModel, setSelectedModel } = useSelectedModelContext();

    const { data: allModels } = useQuery({
        queryKey: ["models"],
        queryFn: getModels
    });

    const PROVIDER_ICONS: Record<string, string> = {
        openai: '/icons/openai.webp',
        gemini: '/icons/gemini-ai.jpg',
        anthropic: '/thirdparty/logos/anthropic.svg',
        deepseek: '/icons/deepseek.png',
        groq: '/icons/llama3.webp',
        hugging_face: '/icons/llama3.webp',
        localhost: '/Icon.svg',
        perplexity: '/Icon.svg'
    };

    const fetchedModelsList = React.useMemo(() => {
        const rawList = allModels?.data || allModels || [];
        return Array.isArray(rawList) ? rawList.map((model: any) => ({
            id: model.model_id || model.id,
            name: model.name,
            icon: PROVIDER_ICONS[model.provider] || '/Icon.svg'
        })) : [];
    }, [allModels]);

    // Set default model once loaded if the current selection isn't configured in the database
    useEffect(() => {
        if (fetchedModelsList.length > 0) {
            const isSelectionValid = fetchedModelsList.some(model => model.id === selectedModel);
            if (!isSelectionValid) {
                setSelectedModel(fetchedModelsList[0].id);
            }
        }
    }, [fetchedModelsList, selectedModel, setSelectedModel]);

    const handleSelectModel = (model: string) => {
        setSelectedModel(model)
    }

    const handleSubmit = async () => {
        if (!inputText.trim()) return;
        const textarea = document.querySelector("textarea");
        if (textarea) {
            textarea.style.height = "auto";
        }
        handleSubmitInput(inputText.trim());
        setInputText("");
    };

    const handleFileSelect = async (
        event: React.ChangeEvent<HTMLInputElement>
    ) => {
        const file = event.target.files?.[0];
        if (!file) return;
        const historyId = history_id
        if (!historyId) {
            return
        }

        try {
            if (file.size > 10 * 1024 * 1024) {
                // 10MB limit
                throw new Error("File size exceeds 10MB limit");
            }
            const user_id = JSON.parse(
                localStorage.getItem("user") || '{"_id":"66ac99b7a2f0a35b8b149299"}'
            )._id
            const bodyFormData = new FormData()
            bodyFormData.append('data', file)
            // bodyFormData.append('conversation_id', historyId as string)
            bodyFormData.append('user_id', user_id)
            const response = await axios.post('/api/chat/upload-file', bodyFormData)
            console.log(response.data)
            setSelectedFile(response.data.file_url);
        } catch (error) {
            console.error("File processing error:", error);
        }
    };
    const isInputDisabled = fetchedModelsList.length === 0;

    return (
        <div className="w-full max-w-4xl mx-auto px-4 pb-6 pt-2 flex flex-col">
            <div className="flex items-center w-full">
                <div className="flex flex-col bg-white dark:bg-[#2E2E2E]/90 rounded-3xl flex-1">
                    <div className="flex flex-row">
                        <div className={`relative flex flex-1 items-center`}>
                            {/* {isRecording && (
                                <div className="flex absolute right-4 items-center gap-2 z-10 px-3 py-1 rounded-full ">
                                    {hasRecognitionSupport && (
                                        <SoundWave isSpeaking={text !== ""} />
                                    )}
                                </div>
                            )} */}

                            {/* Main Input */}
                            <div className={`relative flex-1 h-full flex items-center`}>
                                <ChatArea
                                    value={inputText}
                                    onValueChange={setInputText}
                                    onSubmit={handleSubmit}
                                    onFileSelect={handleFileSelect}
                                    selectedFile={selectedFile}
                                    onRemoveFile={() => setSelectedFile(null)}
                                    isStreaming={isStreaming}
                                    onStop={stopResponse}
                                    disabled={isInputDisabled}
                                />
                            </div>
                        </div>
                    </div>

                    <div className="flex justify-between ml-8 mr-4 mb-2">
                        <div className="flex items-center gap-2 font-light">
                            {/* Internet Search Toggle */}
                            <Badge variant={'outline'} className={`flex items-center gap-2 border-gray-500 rounded-2xl
                ${isInputDisabled ? "opacity-50 cursor-not-allowed pointer-events-none" : "cursor-pointer"}
                ${internetSearchEnabled && "bg-gray-500/50"} py-1.5 font-medium`}
                                onClick={() => !isInputDisabled && setInternetSearchEnabled(!internetSearchEnabled)}
                            >
                                Search
                                <TfiWorld className="text-sm" />
                            </Badge>
                            {/* Thinking Toggle */}
                            <Badge variant={'outline'} className={`flex items-center gap-2 border-gray-500 rounded-2xl
                ${isInputDisabled ? "opacity-50 cursor-not-allowed pointer-events-none" : "cursor-pointer"}
                ${assignmentMode && "bg-gray-500/50"} py-1.5 font-medium`}
                                onClick={() => { if (!isInputDisabled) { setAssignmentMode(!assignmentMode); setBrowserMode(false); } }}
                            >
                                Assignment Mode
                                <LuBrain className="text-base" />
                            </Badge>
                            {/* Browser Toggle */}
                            <Badge variant={'outline'} className={`flex items-center gap-2 border-gray-500 rounded-2xl
                ${isInputDisabled ? "opacity-50 cursor-not-allowed pointer-events-none" : "cursor-pointer"}
                ${browserMode && "bg-blue-500/50"} py-1.5 font-medium`}
                                onClick={() => { if (!isInputDisabled) { setBrowserMode(!browserMode); setAssignmentMode(false); } }}
                            >
                                Browser Control
                                <TfiWorld className="text-base" />
                            </Badge>
                        </div>
                        <ModelSelector
                            models={fetchedModelsList}
                            selectedModel={selectedModel}
                            onSelect={handleSelectModel}
                        />
                    </div>
                </div>
            </div>
        </div>
    )
}

export default ChatInput