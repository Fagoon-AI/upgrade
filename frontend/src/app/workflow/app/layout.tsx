"use client";

import { ReactFlowProvider } from "@xyflow/react";

export default function Layout({ children }: { children: React.ReactNode }) {

    return (
        <ReactFlowProvider>
            {children}
        </ReactFlowProvider>
    )
}