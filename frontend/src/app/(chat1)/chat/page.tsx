"use client"
import { WelcomeScreen } from '@/components/chat/WelcomeScreen'
import { useEffect } from 'react'
import ChatInput from '@/components/chat/chat-input'
import { showErrorToast } from "@/utils/toast"
import { useRouter } from 'next/navigation'
import { useSendMessage, useUpgradeChat } from '../hooks/useUpgradeChat'
import * as chatApi from '@/lib/api/chat'
import { useMutation } from '@tanstack/react-query'

const ChatWelcomeScreen = () => {
    const { resetChat } = useUpgradeChat()
    const router = useRouter();
    const sendMessage = useSendMessage();


    useEffect(() => {
        resetChat()
    }, [])

    const initChatMutation = useMutation({
        mutationFn: async (text: string) => {
            const response = await chatApi.initUpgradeChat();
            return { response, text };
        },

        onSuccess: async ({ response, text }) => {
            const conversationId = response?.data?.conversation_id;
            router.push(`/c/${conversationId}`);

            if (!conversationId || typeof conversationId !== "string") {
                console.error("Invalid conversation_id:", conversationId);
                return;
            }

            try {
                await sendMessage.mutateAsync({
                    conversationId,
                    message: text,
                });

            } catch (e) {
                showErrorToast("Error sending chat");
            }
        },

        onError: () => {
            showErrorToast("Error sending chat");
        },
    });

    return (
        <div className="flex flex-col h-[100dvh]">
            <div className="flex-1 overflow-y-auto p-4">
                <div className="mx-auto max-w-4xl w-full">
                    <WelcomeScreen />
                </div>
            </div>
            <div className="shrink-0">
                <ChatInput history_id='1' handleSubmitInput={(text) => initChatMutation.mutate(text)} />
            </div>
        </div>
    )
}

export default ChatWelcomeScreen