# Frontend Workflow Node Connections Specification

This document outlines the detailed specifications for all workflow nodes available in the system, detailing their required inputs, outputs, and how they should be connected using the Edge mapping schema. 

This specification is designed to guide the frontend development in correctly configuring React Flow nodes and edges to match the backend's `WorkflowGraph` Pydantic schema requirements.

## Core Concepts for Connections (Edges)

When connecting Node A (Source) to Node B (Target), the `WorkflowEdge` payload must specify exactly how the data flows:

1. **Handles (Ports):**
   - `sourceHandle`: The `id` of the output port on the source node (e.g., `response`, `image`, `audio`).
   - `targetHandle`: The `id` of the input port on the target node (e.g., `prompt`, `text`, `body`).

2. **Data Mappings (`data_mappings` array):**
   If the output of Node A is a complex object (like JSON) and Node B only needs a specific string from it, you must use data mappings.
   - `source_field`: The dot-notation path to the data in the source's output payload (e.g., `data.results[0].url` or `output`).
   - `target_field`: The name of the field on the target node's `inputs` object.

---

## 1. Input & Output Nodes (`category: input-output`)

These nodes act as the entry and exit points for data in the workflow graph.

### User Input (`user-input`)
Starts the workflow by prompting the user for text.
- **Outputs (`sourceHandle`):** 
  - `prompt` (Type: prompt) - The user's provided text.

### File Input (`file-input`)
Imports and extracts data from files.
- **Outputs (`sourceHandle`):**
  - `content` (Type: string) - Raw text content.
  - `prompt` (Type: prompt) - Content formatted for LLMs.
  - `metadata` (Type: object) - File details (name, size, type).

### Webhook Output (`webhook-output`)
Receives data from an external webhook.
- **Inputs (`targetHandle`):**
  - `data` (Type: any) - Data to send.
- **Outputs (`sourceHandle`):**
  - `response` (Type: object) - Webhook JSON response.
  - `responsePrompt` (Type: prompt) - Response formatted as a prompt.

### Result Output (`endpoint`)
The terminal node that displays the final result to the user.
- **Inputs (`targetHandle`):**
  - `input` (Type: any) - The final data to display.

### API Input (`api-input`)
Provides initial data for API calls.
- **Outputs (`sourceHandle`):**
  - `response` (Type: string)

---

## 2. Language Models (`category: language-models`)

LLMs process text and generate responses. 
**Available Nodes:** `gpt-4`, `gpt-3.5-turbo`, `claude-3`, `llama-3`, `web-search`, `nano-banana-pro-preview`, `gemini-3.1-pro-preview`.

All LLM nodes share the following connection structure:

- **Inputs (`targetHandle`):**
  - `prompt` (Type: prompt) - **Required.** The main instruction.
  - `systemPrompt` (Type: prompt) - Optional system instructions.
  - `context` (Type: array) - Optional additional context/documents.
  - `url` (Type: prompt) - **Required for `web-search` only.**
- **Outputs (`sourceHandle`):**
  - `response` (Type: string) - The generated text response.

---

## 3. Diffusion / Media Generation (`category: diffusion-models`)

Generates images or videos from text descriptions.
**Available Nodes:** `stable-diffusion-xl`, `dalle-3`, `video-gen`, `veo-3.0-generate-001`.

- **Inputs (`targetHandle`):**
  - `prompt` (Type: prompt) - **Required.** Description of what to generate.
  - `negativePrompt` (Type: prompt) - Optional (SDXL only). What to avoid.
  - `seed` / `reference` (Type: image) - Optional starting image (SDXL/DALL-E).
- **Outputs (`sourceHandle`):**
  - `image` / `video` / `response` (Type: image/string) - The resulting media or URL.

---

## 4. Voice Synthesis & Transcription (`category: voice-synthesis`)

Converts text to audio or audio to text.
**Available Nodes:** `elevenlabs`, `openai-tts`, `fagoon-tts`, `audio-to-text`.

### Text-to-Speech (ElevenLabs, OpenAI TTS, Fagoon-TTS)
- **Inputs (`targetHandle`):**
  - `text` (Type: string) - The text to be spoken.
- **Outputs (`sourceHandle`):**
  - `audio` (Type: audio) - The generated audio file/stream.

### Speech-to-Text (Audio Transcription)
- **Inputs (`targetHandle`):**
  - `audio` (Type: audio) - The audio file to transcribe.
- **Outputs (`sourceHandle`):**
  - `text` (Type: string) - The transcribed text.

---

## 5. Google Workspace Integration (`category: google-workspace`)

Executes actions within Google Workspace apps.

### Send/Reply Email (`send-email`, `reply-email`)
- **Inputs (`targetHandle`):**
  - `to` (Type: string) - **Required.** Recipient.
  - `subject` (Type: string) - **Required.**
  - `body` (Type: string) - **Required.** Email content.
  - `original_message_id` (Type: string) - **Required for `reply-email`.**
- **Outputs (`sourceHandle`):**
  - `response` (Type: string) - Status response.

### Summarise / Get Email Details (`summarise-email`, `get-email-details`)
- **Inputs (`targetHandle`):**
  - `message_id` (Type: string) - **Required.** Conversation ID.
- **Outputs (`sourceHandle`):**
  - `response` (Type: string) - Summary or email details.

### Google Docs (`create-docs`, `get-docs-content`, `write-docs-content`)
- **Inputs (`targetHandle`):**
  - `title` / `initial_content` (For `create-docs`).
  - `document_id` (For `get/write` docs).
  - `text_content` (For `write-docs-content`).
- **Outputs (`sourceHandle`):**
  - `docs_id` (From `create-docs`).
  - `content` (From `get/write` docs).

### Google Drive (`create-drive-folder`)
- **Inputs (`targetHandle`):**
  - `folder_name` (Type: string) - **Required.**
  - `parent_id` (Type: string) - Optional parent folder ID.
- **Outputs (`sourceHandle`):**
  - `folder_id` (Type: string).

---

## Connection Mapping Examples for Frontend Implementation

When building the UI flow in React Flow, the `onConnect` handler must construct the edge payload accurately based on the handles connected.

### Example 1: Simple LLM Chain (User Input -> GPT-4)
*User provides a prompt, GPT-4 processes it.*
- **Source Node:** `user-input`
- **Target Node:** `gpt-4`
- **Edge Payload Configuration:**
  ```json
  {
    "source": "node_user_input_1",
    "target": "node_gpt4_1",
    "sourceHandle": "prompt",
    "targetHandle": "prompt",
    "data_mappings": [
      {
        "source_field": "output",
        "target_field": "prompt",
        "transform": "string"
      }
    ],
    "auto_map": true
  }
  ```

### Example 2: LLM generating Image (GPT-4 -> DALL-E 3)
*GPT-4 writes a scene description, DALL-E 3 renders it.*
- **Source Node:** `gpt-4`
- **Target Node:** `dalle-3`
- **Edge Payload Configuration:**
  ```json
  {
    "source": "node_gpt4_1",
    "target": "node_dalle3_1",
    "sourceHandle": "response",
    "targetHandle": "prompt",
    "data_mappings": [
      {
        "source_field": "output",
        "target_field": "prompt"
      }
    ]
  }
  ```

### Example 3: Complex JSON parsing (Webhook -> Send Email)
*A webhook receives a complex JSON payload, and we need to map specific fields to an email node.*
- **Source Node:** `webhook-output`
- **Target Node:** `send-email`
- **Edge Payload Configuration:**
  ```json
  {
    "source": "node_webhook_1",
    "target": "node_email_1",
    "sourceHandle": "response",
    "targetHandle": "to",
    "data_mappings": [
      {
        "source_field": "data.customer.email",
        "target_field": "to"
      },
      {
        "source_field": "data.customer.message",
        "target_field": "body"
      }
    ]
  }
  ```