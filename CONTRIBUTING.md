# Contributing to Fagoon AI Agents Workflow

Thank you for your interest in contributing to Fagoon! As a contributor, your efforts help make Fagoon a more powerful, secure, and user-friendly platform for everyone.

By participating in this project, you agree to abide by our codebase standards, security policies, and code of conduct.

---

## 1. Getting Started

Fagoon uses a modern Python 3.12+ stack managed with `uv` for lightning-fast package and dependency management.

### Prerequisites
- Python 3.11 or 3.12
- `uv` (Fast Python package installer: `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Docker & Docker Compose (for running dependencies locally)

### Setup Your Local Environment
1.  **Fork and Clone**:
    ```bash
    [git clone https://github.com/Fagoon-AI/upgrade.git
    cd upgrade
    ```
2.  **Synchronize Dependencies**:
    Initialize the virtual environment and install all packages (including development packages):
    ```bash
    uv sync --extra full
    ```
3.  **Local Configurations**:
    Create your local environment file:
    ```bash
    cp .env.example .env
    ```
    *(Note: `.env` and `data/config.json` are globally ignored and should never be committed.)*

---

## 2. Core Architecture Rules & Patterns

To ensure a clean, performant, and stable codebase, please strictly adhere to our established architecture invariants:

*   **FastAPI Lifespan Singletons**: Heavy clients (such as database pools, HTTP clients, and AI model registries) must be initialized once during the application lifespan (`src/launch_server.py`) and attached to `app.state`. **Do NOT** instantiate them per request.
*   **Decoupled Architecture**: Maintain a strict separation of layers:
    *   **Routers** (`src/api/v1/routers/`): Handle HTTP routing and request validation (Pydantic). No core business logic should reside here.
    *   **Services** (`src/services/`): Handle the core orchestration and business workflows.
*   **Dual-Mode Runtime (Lite & Full)**: Business logic modules must **never** import `redis` or `celery` directly. They should route all state and concurrency actions through the dynamic abstractions provided in `app.state.limiter`, `app.state.queue`, and `app.state.cache`. This maintains clean operation in Lite Mode.

---

## 3. Coding & Security Standards

*   **Pydantic & Schemas**: Always use explicit, strict types. Do not bypass Pydantic validation.
*   **Credential Handling**: Never hardcode API keys, secrets, or bearer tokens.
    *   All configured connection tokens must be saved encrypted in the PostgreSQL `Connection` table via Fernet.
    *   Use `resolve_api_key()` to dynamically resolve user credentials from the database.
*   **Dynamic Inputs**: When resolving prompts or text parameters inside custom model nodes, always wrap the value using `ensure_string` (imported from `src.services.workflow_engine.nodes.base`) to gracefully parse and sanitize incoming dictionaries or lists.

---

## 4. Submitting a Pull Request

We follow a rigorous, linear development cycle to maintain a pristine history:

1.  **Create a Branch**:
    Keep branches focused on a single logical change (e.g., `feat/add-slack-tool` or `fix/jwt-expiration`).
2.  **Add & Update Tests**:
    Write clear tests for any new features or bug fixes. Run the complete test suite locally to verify:
    ```bash
    uv run pytest tests
    ```
3.  **Stage Surgically**:
    Do not use `git add .` or stage arbitrary files. Explicitly stage only the modified files relevant to your change:
    ```bash
    git add src/services/my_service.py tests/test_my_service.py
    ```
4.  **Descriptive Commits**:
    Write clear, concise commits focused on *why* a change was made rather than *what*:
    ```text
    fix: handle custom model fallbacks in chat orchestrator

    - Dynamically resolve model-provider pairings in API resolver to bypass 404s
    ```
5.  **Open the PR**:
    Submit your Pull Request against the `main` branch. A maintainer will review your code, run the CI checks, and work with you on merging!

Thank you for contributing! 🚀
