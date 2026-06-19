"use client";

import { ChatProvider } from "./hooks/useUpgradeChat";

export default function Layout({ children }: { children: React.ReactNode }) {

    return (
        <ChatProvider>
            {children}
        </ChatProvider>
    )
}