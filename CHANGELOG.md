# Changelog

All notable changes to the Fagoon AI Agents Workflow project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.7] - 2026-06-22

### Fixed
*   **LifeSpan Global Imports**: Resolved a critical test and startup exception (`UnboundLocalError: cannot access local variable 'asyncio'`) by promoting the `asyncio` import globally to the top of `src/launch_server.py`.
*   **Open Source Readiness**: Purged historical occurrences of raw credentials and metadata across all git branches.

---

## [2.1.6] - 2026-06-22

### Added
*   **Graceful RAI Safety Handling**: Intercepted Google's strict Responsible AI (RAI) safety filter blocks inside the Veo video generator tool handler. It now dynamically streams a polite, helpful prompt-rephrase recommendation inside the chat bubble instead of throwing a technical traceback.

---

## [2.1.5] - 2026-06-22

### Fixed
*   **Variable Scoping Conflict**: Resolved an `UnboundLocalError: cannot access local variable 'uuid'` scoping collision inside the `VideoGenerationHandler` by removing a redundant local `import uuid` statement.

---

## [2.1.4] - 2026-06-22

### Added
*   **Dynamic WebSearch Resolver**: Completely removed the hardcoded Groq and LLaMA dependencies from the web search handler. The system now dynamically resolves the user's active, database-configured selected model and provider (e.g. Gemini 2.5) to generate query alternatives on-the-fly.
*   **Veo Credentials Resolution**: Fixed a video generator crash by dynamically resolving the user's custom database-configured Gemini API key and passing it to the Veo generator config on initialization.

---

## [2.1.3] - 2026-06-22

### Added
*   **Image Generation Rule-Based Path**: Added a high-speed, direct rule-based matcher for image generation prompts. This bypasses the LLM classification pipeline entirely for direct instructions (e.g. "draw a cat"), improving response time and providing 100% routing accuracy.
*   **Tool Analyzer Key Resolution**: Refactored the query analyzer LLM setup to dynamically resolve and use the user's custom database-configured API keys. This prevents tool-select failovers from falling back to local Ollama models when system-wide keys are absent.

---

## [2.1.2] - 2026-06-22

### Fixed
*   **Ollama Fallback Model**: Registered `FALLBACK_MODEL_NAME` and `FALLBACK_MODEL_PROVIDER` directly in the settings class to dynamically load options from `config.json`. Refactored `llm.py` failover logic to request the user's CLI-selected fallback model instead of the deprecated, hardcoded `gemma:2b` model.

---

## [2.1.0] - 2026-06-22

### Added
*   **General CORS Support**: Replaced hardcoded origins in `src/launch_server.py` with an adaptive combination of system configurations and a dynamic regex that seamlessly matches and allows any secure ngrok tunnel subdomains (`*.ngrok-free.dev`, `*.ngrok.io`, `*.ngrok-free.app`), enabling smooth self-hosting and multi-user configurations.
*   **Alembic Migration Stamp**: Aligned database schema versioning with PostgreSQL heads using `alembic stamp heads` to prevent duplicate-table collisions on startup.

---

## [2.0.6] - 2026-06-20

### Fixed
*   **Security & Credential Removal**: Scrubbed commented OpenAI API keys and removed untracked local metadata and configuration outputs from the repository before open sourcing.
