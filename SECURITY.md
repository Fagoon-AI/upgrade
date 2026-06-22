# Security Policy (SECURITY.md)

Welcome to the Fagoon AI Agents Workflow platform! As an open-source project, maintaining the security and integrity of our codebase and deployment pipeline is a top priority. This document outlines our security standards, credential management policies, and how to safely report vulnerabilities.

---

## 1. Secrets & Credentials Protection Invariant

**CRITICAL INVARIANT:** Under no circumstances should real production secrets, private keys, API keys, or personal tokens be committed to this repository.

*   **API Key Patterns**: Do not commit strings matching common API key formats:
    *   OpenAI / Anthropic: `sk-[a-zA-Z0-9_-]{32,}`
    *   Google Gemini / Vertex: `AIza[a-zA-Z0-9_-]{30,}`
*   **Local Configurations**: Keep all local configuration adjustments (such as `data/config.json` and `.env`) out of git. They are ignored globally via `.gitignore`.
*   **PR Review Requirement**: All Pull Requests (PRs) must be audited to ensure that no testing scripts, mock JSONs, or documentation files contain real credentials. Always use placeholders like `YOUR_GEMINI_API_KEY` or `YOUR_OPENAI_API_KEY` in files destined for pull requests.

---

## 2. Connection Credentials Encryption (at Rest)

To guarantee high security, Fagoon implements a strict database-only encrypted storage model for all configured integrations (such as Gmail, Google Sheets, Slack, Perplexity, etc.):

*   **Fernet Encryption**: All credentials belonging to a connection are encrypted at rest inside the `Connection` table (`src/models/sql/workflow/connection.py`) using **Fernet symmetric encryption** (AES-128-CBC + HMAC-SHA256).
*   **Lifespan & Decryption**: Credentials are only decrypted in-memory during workflow node execution (using `crypto.decrypt()`) or when needed by background tasks. 
*   **Zero File Leakage**: Decrypted credentials must **never** be written to disk or saved as temporary files on host systems. They reside strictly in-memory during runtime.

---

## 3. Dynamic Configuration & CLI Key Management

In Lite Mode (designed for single-process local setups), secrets are handled dynamically to ensure zero-overhead secure deployments:

*   **Auto-Generation**: Secrets (such as `JWT_SECRET`, `ENCRYPTION_KEY`, and `EVOLUTION_API_KEY` for the WhatsApp gateway) are automatically generated on first boot and written to `<DATA_DIR>/config.json`.
*   **Symmetric Encryption on Disk**: Sensitive keys imported or migrated from `.env` files into `config.json` by the CLI are automatically Fernet-encrypted.
*   **Secure Environment Passing**: The CLI (`fagoon_cli/main.py`) decrypts these credentials on-the-fly and passes them as environment variables to container runtimes. The backend entrypoint (`deploy/entrypoint.sh`) also safely decrypts any `fernet:` prefixed keys during container startup.

---

## 4. Reporting a Vulnerability

If you discover a security vulnerability in this project, **please do not open a public issue.** Instead, report it privately to ensure it can be patched before public disclosure.

*   **Email**: Send a detailed description of the vulnerability, reproduction steps, and potential impact to **admin@fagoondigital.com** (or contact the maintainers).
*   **Response**: We will acknowledge your report within 48 hours and work with you to analyze and resolve the issue under a responsible disclosure policy.

---

Thank you for helping us keep Fagoon safe for everyone!
