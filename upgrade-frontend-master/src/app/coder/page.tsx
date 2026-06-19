"use client";

import React, { useState, useEffect, useRef } from "react";
import { CircleDot } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { generateCode } from "@/lib/api/coder";
import { getModels } from "@/lib/api/models";
import { TerminalInput } from "@/components/coder/TerminalInput";
import { CodeOutput } from "@/components/coder/CodeOutput";
import ModelSelector from "@/components/chat/modalSelector";
import { useSelectedModelContext } from "@/contexts/SelectedModelContext";

const PROVIDER_ICONS: Record<string, string> = {
  openai: "/icons/openai.webp",
  gemini: "/icons/gemini-ai.jpg",
  anthropic: "/thirdparty/logos/anthropic.svg",
  deepseek: "/icons/deepseek.png",
  llama: "/icons/llama3.webp",
  localhost: "/Icon.svg",
  perplexity: "/Icon.svg",
};

export default function Home() {
  const [command, setCommand] = useState("");
  const [activeCode, setActiveCode] = useState(
    "// Welcome to Fagoon Code.\n// Ask me to build something, and the code will appear here."
  );
  const [viewMode, setViewMode] = useState<"code" | "preview">("code");
  const [logs, setLogs] = useState([
    { type: "info", text: "[⚡ Fagoon Code Initialized] System online." },
    { type: "success", text: "[✓ System] Ready for commands." },
  ]);
  const logEndRef = useRef<HTMLDivElement>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [manualSelectionMade, setManualSelectionMade] = useState(false);
  
  const { selectedModel, setSelectedModel } = useSelectedModelContext();

  // TanStack Query to Fetch Models
  const { data: allModels } = useQuery({
    queryKey: ["models"],
    queryFn: getModels,
  });

  const fetchedModelsList = React.useMemo(() => {
    const rawList = allModels?.data || allModels || [];
    return Array.isArray(rawList)
      ? rawList.map((model: any) => ({
          id: model.model_id || model.id,
          name: model.name,
          provider: model.provider,
          icon: PROVIDER_ICONS[model.provider] || "/Icon.svg",
        }))
      : [];
  }, [allModels]);

  // TanStack Query Mutation for code generation
  const codeMutation = useMutation({
    mutationFn: generateCode,
  });

  const simulateWork = async (cmd: string) => {
    let delay = 0;
    const addLog = (text: string, type = "info") => {
      delay += 400 + Math.random() * 800;
      setTimeout(() => {
        setLogs((prev) => [...prev, { text, type }]);
      }, delay);
    };

    setIsProcessing(true);
    addLog(
      `[⚡ Fagoon Code Intercept]: Routing natural language to AI Backend...`,
      "warning"
    );

    try {
      const currentModel = fetchedModelsList.find(m => m.id === selectedModel);
      if (!currentModel) throw new Error("No model selected");

      // Execute via TanStack Mutation
      const data = await codeMutation.mutateAsync({
        prompt: cmd,
        llm_config: {
          model_id: currentModel.id,
          provider: currentModel.provider,
          model_name: currentModel.name
        }
      });

      const steps = data.steps || [];
      steps.forEach((step: string) => {
        let type = "info";
        if (step.includes("[✓")) type = "success";
        else if (step.includes("[✍️")) type = "warning";
        else if (step.includes("[✗")) type = "error";
        else if (step.includes("[⚡")) type = "info";
        addLog(step, type);
      });

      if (data.code) {
        setTimeout(() => setActiveCode(data.code), delay + 300);
      }
    } catch (err: any) {
      addLog(`[✗ System]: ${err.message || "AI Backend Unreachable."}`, "error");
    } finally {
      setTimeout(() => setIsProcessing(false), delay + 500);
    }
  };

  const handleCommand = (e: React.FormEvent) => {
    e.preventDefault();
    if (!command.trim() || isProcessing || fetchedModelsList.length === 0 || !manualSelectionMade) return;

    setLogs((prev) => [...prev, { text: `> ${command}`, type: "command" }]);
    simulateWork(command);
    setCommand("");
  };

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="min-h-screen font-mono flex flex-col p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-8 shrink-0">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">Fagoon Code</h1>
          <p className="text-muted-foreground mt-1 font-sans text-sm">Enterprise AI Developer</p>
        </div>
        <div className="flex items-center gap-4 text-sm shrink-0">
        </div>
      </div>

      {/* Main Interface Layout - Removed sidebar wrapper */}
      <main className="flex-1 flex flex-col lg:flex-row gap-6 h-full min-h-[600px] overflow-hidden">
        {/* Terminal Input Area (Modularized) */}
        <TerminalInput
          logs={logs}
          command={command}
          setCommand={setCommand}
          onSubmit={handleCommand}
          logEndRef={logEndRef}
          isProcessing={isProcessing}
          disabled={fetchedModelsList.length === 0}
          noModelSelected={fetchedModelsList.length > 0 && !manualSelectionMade}
          models={fetchedModelsList}
          selectedModel={selectedModel}
          onSelectModel={(modelId) => {
            console.log("Selected model in Coder:", modelId);
            setSelectedModel(modelId);
            setManualSelectionMade(true);
          }}
        />

        {/* Code Output / Preview Area (Modularized) */}
        <CodeOutput
          activeCode={activeCode}
          viewMode={viewMode}
          setViewMode={setViewMode}
        />
      </main>
    </div>
  );
}
