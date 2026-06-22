<h1 align="center">
  <img src="frontend/public/Icon.svg" alt="Upgrade Icon" width="45" height="45" style="vertical-align: middle; margin-right: 10px;" />
  Upgrade
</h1>

<p align="center">
  <strong>Self-hosted AI platform with workflow automation, agents, chat, and API generation.</strong>
</p>

<p align="center">
  Build AI workflows visually, publish them as REST APIs, deploy agents, and chat with LLMs — all running on your own machine.
</p>

<p align="center">
  <video src="frontend/public/Upgrade.mp4" width="100%" controls autoplay muted loop></video>
</p>

---

## Quick Start

### Prerequisites

- **Docker Desktop** — [Download here](https://www.docker.com/products/docker-desktop/)
- **Python 3.11+** — [Download here](https://www.python.org/downloads/)
- **pipx** (recommended) — Install with: `pip install pipx`

### Install & Run

```bash
# Install the CLI
pipx install fagoon-upgrade

# Start the platform
fagoon up
```

On first run, you'll see a setup wizard:

```
  Welcome to Fagoon!
  Let's set up your AI platform.

  How would you like to power your AI?
  1) I have an API key (OpenAI, Gemini, Groq, etc.)
  2) Use local Ollama model (free, runs on your machine)
  3) Skip for now (configure later in the UI)

  Choose [1/2/3]:
```

### Access the Platform

| Service  | URL                          |
|----------|------------------------------|
| Frontend | http://localhost:3000        |
| Backend  | http://localhost:8000        |

---

## Features

- **Visual Workflow Builder** - Drag-and-drop canvas with 20+ node types
- **Workflow-as-API** - Publish any workflow as a REST endpoint with API key auth
- **AI Agents** - Conversational agents with memory and tool use
- **Chat Interface** - Chat with any LLM provider through a unified UI
- **Multi-Provider** - OpenAI, Gemini, Groq, Anthropic, Ollama
- **Self-Hosted** - Your data stays on your machine

---

## CLI Commands

```bash
fagoon up                    # Start the platform (lite mode)
fagoon up --full             # Start with Redis + Celery (multi-worker)
fagoon up --ollama           # Start with local Ollama LLM
fagoon down                  # Stop the platform
fagoon logs -f               # Follow live logs
fagoon status                # Check if running
fagoon update                # Pull latest version and restart
fagoon config set KEY=VALUE  # Set configuration
fagoon config show           # Show current config
fagoon db set-url URL        # Switch database
```

---

## Workflow-as-API

Publish any workflow as a callable REST API:

```bash
curl -X POST http://localhost:8000/api/v1/workflow-api/your-slug/execute \
  -H "X-API-Key: wfapi_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello from my app"}'
```

Response:

```json
{
  "success": true,
  "execution_id": "uuid",
  "status": "COMPLETED",
  "output": {
    "output_text": "AI generated response",
    "model": "gemini-2.5-flash"
  },
  "usage": { "duration_ms": 2500 }
}
```

---

## Deployment Modes

### Lite Mode (Default)

Single-user, no Redis/Celery. Perfect for personal use.

```bash
fagoon up
```

### Full Mode

Multi-worker with Redis + Celery. For production.

```bash
fagoon up --full
```

### With Ollama (Local LLM)

Free, offline AI using local models.

```bash
fagoon up --ollama
```

---

## Docker Compose (Direct)

```yaml
services:
  app:
    image: ghcr.io/fagoon-ai/upgrade:2.0.4
    ports:
      - "8000:8000"
      - "3000:3000"
    environment:
      LITE_MODE: "true"
      DATABASE_URL: postgresql+asyncpg://fagoon:fagoon@db:5432/fagoon
    depends_on:
      db: { condition: service_healthy }

  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: fagoon
      POSTGRES_PASSWORD: fagoon
      POSTGRES_DB: fagoon
    volumes:
      - fagoon_db:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U fagoon"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  fagoon_db:
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| LITE_MODE | true | true = single-process, false = Redis+Celery |
| DATABASE_URL | auto | PostgreSQL connection string |
| JWT_SECRET | auto | Secret for JWT tokens |
| GEMINI_API_KEY | — | Google Gemini API key |
| OPENAI_API_KEY | — | OpenAI API key |
| GROQ_API_KEY | — | Groq API key |
| OLLAMA_BASE_URL | — | Ollama server URL |
| WEB_CONCURRENCY | 1 | Number of workers |

---

## Troubleshooting

**"Cannot connect to Docker daemon"** — Start Docker Desktop and wait for it to load.

**"Port 3000/8000 already in use"** — Stop other services on those ports.

**Platform won't start:**

```bash
fagoon logs -f     # Check logs
fagoon down        # Stop
fagoon up          # Restart
```

**Reset everything:**

```bash
fagoon down
docker volume rm fagoon_db fagoon_data
fagoon up
```

---

## Tech Stack

- **Backend:** Python, FastAPI, SQLAlchemy, PostgreSQL, pgvector
- **Frontend:** Next.js, React, TailwindCSS, React Flow
- **Workflow Engine:** Custom DAG executor with 20+ node types
- **Task Queue:** Celery + Redis (full mode)
- **Container:** Docker, Docker Compose

---

## Links

- **Website:** [fagoonai.com](https://fagoonai.com)
- **PyPI:** [pypi.org/project/fagoon-upgrade](https://pypi.org/project/fagoon-upgrade)
- **Docker:** `docker pull ghcr.io/fagoon-ai/upgrade:2.0.4`
- **GitHub:** [github.com/Fagoon-AI/upgrade](https://github.com/Fagoon-AI/upgrade)

---

## Founder's Note

> "When Big Tech started restricting their technology, AI lost its most important feature: inclusion. AI shouldn't belong to one corporation or one country, it belongs to everyone.
>
> Fagoon AI stands firmly by the open source community. To prove it, we are open sourcing one of our largest internal projects: Upgrade.
>
> Upgrade allows you to host and modify open source/API models, craft powerful AI agents, and deploy them instantly via API or WhatsApp. We're putting the power back in the hands of the developers, and we will be continuously rolling out new packages and updates.
>
> Let's keep AI open."
>
> **Shekhar Adhikari**  
> Founder of Fagoon AI

## License

[Apache-2.0 license](https://www.apache.org/licenses/LICENSE-2.0)
