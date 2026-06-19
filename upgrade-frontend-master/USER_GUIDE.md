# Fagoon AI & Upgrade Platform — User Guide & Documentation

Welcome to the official documentation for the **Fagoon AI & Upgrade Platform**. This comprehensive guide provides an overview of all the powerful features available in the project, along with step-by-step instructions on how to access, configure, and master them.

---

## Table of Contents
1. [Core Features Overview](#1-core-features-overview)
2. [Visual Workflow Canvas & Orchestrator (DAGs)](#2-visual-workflow-canvas--orchestrator-dags)
3. [Workflow API & Webhook Integrations](#3-workflow-api--webhook-integrations)
4. [Enterprise Vibe Coder (Sandbox Playground)](#4-enterprise-vibe-coder-sandbox-playground)
5. [Standard Chat Portal (Multi-Model & RAG)](#5-standard-chat-portal-multi-model--rag)
6. [Autonomous AI Agents Chat Hub](#6-autonomous-ai-agents-chat-hub)
7. [Model Configuration Portal (Manage Models)](#7-model-configuration-portal-manage-models)
8. [User Settings & Preferences](#8-user-settings--preferences)

---

## 1. Core Features Overview

The platform is designed to be a unified, enterprise-grade portal for AI orchestration, development, and integration. It bridges high-level visual workflow construction (DAGs) with direct code sandbox synthesis, chatbot channels, and secure external API endpoints.

```
                  ┌────────────────────────────────────────┐
                  │          Fagoon AI Dashboard           │
                  └───────────────────┬────────────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         ▼                            ▼                            ▼
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│ Workflow Canvas │          │   Vibe Coder    │          │  Streaming Chat │
│  (Visual DAGs)  │          │(Real-time Apps) │          │ (Knowledge Base)│
└────────┬────────┘          └─────────────────┘          └─────────────────┘
         │
         ▼
┌─────────────────┐
│  Published API  │
│(cURL, Python, JS)│
└─────────────────┘
```

---

## 2. Visual Workflow Canvas & Orchestrator (DAGs)

The **Workflow Builder** is a drag-and-drop Directed Acyclic Graph (DAG) construction kit where you can chain together complex multi-modal nodes into automated pipelines.

### How to Access:
*   Click the **Workflows** icon on the navigation sidebar, or navigate directly to `/workflow`.

### Canvas Node Types Available:
*   **LLMs / Generative Models:** Deep integrations with OpenAI, Gemini, Anthropic, Groq, and Perplexity.
*   **Multimedia Generators:** Veo Video, Imagen, ElevenLabs (Text-to-Speech), and Kokoro Speech.
*   **Tools & Agents:** Deep Research, Web Search, Code Interpreters, and Mermaid flowchart generator nodes.
*   **Google Workspace Connectors:** Read/Write Gmail messages, modify Google Docs, and list files inside Google Drive.

### Premium Developer Features:
1.  **Iterative Sandbox Debugging (Pin Output):**
    *   *What it is:* Pinning caches a node’s generated output.
    *   *Why use it:* Running expensive/slow nodes (like Veo video generation) costs money and time. Pinning "mocks" that node's execution on subsequent canvas runs, immediately returning the saved value to downstream nodes so you can refine prompt details instantly.
    *   *How to use:* Run a workflow, select the node in the logs, and click the **Pin** button. To disable, click the active orange **`📌 Pinned`** badge on the canvas card to toggle it off.
2.  **Telemetry Terminal Logs:**
    *   Displays real-time, colored execution logs and compilation progress directly on the visual panel. Includes auto-scroll capabilities to focus on active nodes.

---

## 3. Workflow API & Webhook Integrations

Once you have constructed a functional AI pipeline inside the visual canvas, you can publish it as a **fully-fledged REST API endpoint** to trigger it programmatically from your own external websites or servers.

### How to Access:
1.  Save your workflow inside the visual canvas `/workflow`.
2.  Once saved, click the **`🔑 API Integration`** button on the header control bar.

### Available Controls inside the API Panel:
*   **Dynamic Slugs:** Backend auto-generates a human-friendly URL slug mapped to your workflow.
*   **One-Time Secret Key:** Generates a secure API key shown strictly **once** upon creation for maximum safety.
*   **Webhook Endpoints:** Copy the exact Webhook Endpoint URL formatted with your slug:
    ```
    https://fagoon.tech/api/v1/workflow-api/{slug}/execute
    ```
*   **Revocation Control:** Instantly destroy active credentials via the **Revoke Credentials** option to immediately block external connections if keys are compromised.

### Header Authentication Payload Structure:
To run your published workflow from any script, send a `POST` request with the following headers:
```bash
curl -X POST "https://fagoon.tech/api/v1/workflow-api/{slug}/execute" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"input": "Describe a spaceship"}'
```

---

## 4. Enterprise Vibe Coder (Sandbox Playground)

The **Vibe Coder** is a visual sandbox page built to compile, render, and preview interactive HTML5 and React single-page applications live, utilizing high-speed AI streaming.

### How to Access:
*   Click the **Vibe Coder** icon on the navigation sidebar, or navigate directly to `/coder`.

### Notable Interface Capabilities:
*   **Contextual Model selector:** Allows selecting your model preset showing provider logo assets. Includes **pollution guards** that auto-override and default selection to the first valid model on loading.
*   **Double-Viewport Design:**
    *   *Code View:* Custom styled `ScrollArea` displaying formatted syntax with a one-click **Copy Code** button.
    *   *Preview Render View:* Sandboxed standard `iframe` executing the compiled HTML5 elements live.
*   **Token-Streaming Response:** Uses optimized SSE (Server-Sent Events) chunk decoding to append code characters live on your screen as the AI types, stripped dynamically of Markdown backticks so pages load immediately.
*   **Conversation History Memory:** Appends prompts and completed raw scripts to the context memory dynamically, letting you give incremental visual directives (e.g. *"Make the score layout red"* or *"Add a restart button"*) with perfect AI recall.

---

## 5. Standard Chat Portal (Multi-Model & RAG)

The **Standard Chat** is a general conversational interface designed for versatile, day-to-day AI interactions, research, and prompt engineering.

### How to Access:
*   Navigate to the home route `/chat` or open a saved conversation from the sidebar history `/c/{historyId}`.

### Standard Features:
*   **Dynamic Multi-Model Selection:** Seamlessly switch between configured models (e.g. OpenAI GPT-4o, Llama-3, Gemini, Anthropic, DeepSeek) directly on the chat input bar mid-conversation or for a new chat session to compare reasoning, outputs, or generation speed.
*   **File Upload Knowledge Base:** Attach files and binary documents directly to your chat input. Validates a strict **10MB size limit** before securely uploading file buffers to private Google Cloud Storage (GCS) buckets.
*   **Incomplete Chunk Buffering:** Streaming engine uses a trailing buffer `lines.pop()` to assemble sliced packets, ensuring that rapid LLM text generation is rendered beautifully without JSON parsing errors.
*   **Floating Branding:** Includes the platform-wide **`Powered by Fagoon AI`** floating indicator in the bottom-right corner.

---

## 6. Autonomous AI Agents Chat Hub

The **AI Agents Hub** is a specialized environment for interacting with autonomous, goal-directed, pre-configured **AI Agents** designed to perform specific enterprise tasks in loops.

### How to Access:
*   Click on **Agents** (or your selected Agent channel) inside the sidebar navigation panel, or go directly to `/agents`.

### Key Capabilities & Mechanics:
*   **Multi-Step Event Parsing:** Styled to handle autonomous multi-step execution responses line-by-line (`TOOL_SELECTION`, `STATUS`, `LLM_RESPONSE`, `IMAGE`, `ERROR`).
*   **Collapsible System logs:** Live-scrolling collapsible terminal screens nested inside messages showing exact tool selections and background agent tasks.
*   **Rich Media Sandbox:** Directly displays generated image attachments and handles custom embedded video player clips (such as those returned from long-running background video tasks).

---

## 7. Model Configuration Portal (Manage Models)

A centralized, secure admin console to add and modify model setups and coordinate permissions across specific platform features.

### How to Access:
*   Click **Manage Models** in the sidebar navigation, or go directly to `/manage-models`.

### Supported Configuration Fields:
1.  **Configuration Name:** Friendly display label (e.g. `GPT-4o Production`).
2.  **Provider Selector:** Select your vendor (OpenAI, Gemini, Anthropic, Perplexity, etc.). Supports OpenRouter-style configurations by enabling a custom **Base URL** override.
3.  **Model ID:** The exact system key of the model (e.g. `gpt-4o-2024-05-13`, `gemini-1.5-pro`).
4.  **API Key:** Secure password field (securely masked as dots `••••••••` during retrieval).
5.  **Feature Access Toggles:** Restrict or grant model capabilities across specific workspaces:
    *   *Chat:* Enable for conversational agent channels.
    *   *Workflow:* Enable to construct DAG pipelines.
    *   *Coder:* Enable to load within the Vibe Coder playground.

---

## 8. User Settings & Preferences

Tailor the AI's persona, system behavior, and platform appearance to match your specific workflow.

### How to Access:
*   Click on your profile avatar in the sidebar footer and click **Profile**, or navigate to `/profile`.

### Custom Parameters:
*   **AI Response Tone:** Modify the conversational voice across **casual, professional, formal, or friendly** presets.
*   **Global System Prompt Override:** Inject custom constraints (e.g. *"Always output code in TypeScript"* or *"Summarize things in bullet points"*) globally across all models.
*   **Display Theme Selector:** Toggle between dark mode, light mode, or system themes seamlessly.

---

*Powered by **Fagoon AI*** 🚀
