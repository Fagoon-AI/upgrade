# Fagoon Upgrade

**Self-hosted AI platform with workflow automation, agents, chat, and API generation.**

Build AI workflows visually, publish them as REST APIs, deploy agents, and chat with LLMs — all running on your own machine.

---

## Quick Start

### Prerequisites

- **Docker Desktop** — [Download here](https://www.docker.com/products/docker-desktop/)
- **Python 3.10+** — [Download here](https://www.python.org/downloads/)
- **pipx** (recommended) — Install with: `pip install pipx`

### Install & Run

```bash
<<<<<<< HEAD
pipx install fagoon-upgrade
fagoon up                 # lite mode: no Redis, no Celery, zero env required
fagoon up --ollama        # add the local Gemma fallback LLM
```
Open http://localhost:8000 and complete the setup wizard (LLM key + features).
Secrets are auto-generated; the database URL and config live in `~/.fagoon`.
=======
# Install the CLI
pipx install fagoon-upgrade
>>>>>>> feat/dual-mode

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

Pick your option and Fagoon starts automatically.

### Access the Platform

| Service  | URL                          |
|----------|------------------------------|
| Frontend | http://localhost:3000        |
| Backend  | http://localhost:8000        |

---

## Features

### Visual Workflow Builder
Drag-and-drop workflow canvas to build AI automations. Connect LLM nodes, filters, loops, and integrations visually.

### Workflow-as-API
Publish any workflow as a REST API endpoint with one click. Get an API key and endpoint URL — call it from any app, any language.

```bash
curl -X POST https://your-domain/api/v1/workflow-api/my-workflow/execute \
  -H "X-API-Key: wfapi_xxxxx" \
  -H "Content-Type: application/json" \
  -d '{"input": "Summarize this document"}'
```

### AI Agents
Build and deploy conversational AI agents with memory, tool use, and multi-turn conversations.

### Chat Interface
Chat with any LLM provider (OpenAI, Gemini, Groq, Anthropic, Ollama) through a unified interface.

### Multi-Provider Support
Use any combination of LLM providers. Switch between them per workflow or per agent.

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

## Configuration

Configuration is stored in `~/.fagoon/config.json`. Set values via CLI or the web UI.

### LLM Provider Keys

```bash
fagoon config set GEMINI_API_KEY=your-key-here
fagoon config set OPENAI_API_KEY=your-key-here
fagoon config set GROQ_API_KEY=your-key-here
```

Or configure through the web UI at http://localhost:3000 after login.

### Using Local Ollama

Run with the Ollama profile to use free local models:

```bash
fagoon up --ollama
```

This starts an Ollama container alongside Fagoon. The Gemma 2B model is available as a fallback when no API keys are configured.

---

## Deployment Modes

### Lite Mode (Default)

Single-user, single-process. No Redis or Celery required. Perfect for personal use and small teams.

```bash
fagoon up
```

### Full Mode

Multi-worker with Redis and Celery for background task processing. For production deployments and teams.

```bash
fagoon up --full
```

---

## Using Docker Compose Directly

If you prefer not to use the CLI:

### Lite Mode

```yaml
# docker-compose.yml
services:
  app:
    image: ghcr.io/fagoon-ai/upgrade:2.0.0
    ports:
      - "8000:8000"
      - "3000:3000"
    environment:
      LITE_MODE: "true"
      DATABASE_URL: postgresql+asyncpg://fagoon:fagoon@db:5432/fagoon
      JWT_SECRET: "your-secret-here"
      GEMINI_API_KEY: "your-key-here"
    depends_on:
      db:
        condition: service_healthy

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

```bash
docker compose up -d
```

### Full Mode

```yaml
# docker-compose.full.yml
services:
  app:
    image: ghcr.io/fagoon-ai/upgrade:2.0.0
    ports:
      - "8000:8000"
      - "3000:3000"
    environment:
      LITE_MODE: "false"
      DATABASE_URL: postgresql+asyncpg://fagoon:fagoon@db:5432/fagoon
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/1
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started

  worker:
    image: ghcr.io/fagoon-ai/upgrade:2.0.0
    command: uv run celery -A src.core.celery_app worker -P eventlet -c 50
    environment:
      LITE_MODE: "false"
      DATABASE_URL: postgresql+asyncpg://fagoon:fagoon@db:5432/fagoon
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/1
    depends_on:
      app:
        condition: service_healthy

  redis:
    image: redis:7-alpine

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

```bash
docker compose -f docker-compose.full.yml up -d
```

---

## Workflow API — Turn Any Workflow Into an API

### 1. Build a Workflow
Open http://localhost:3000, create a workflow in the visual canvas.

### 2. Publish as API
Click **API Integration** → **Generate API Key & Slug**. Copy the API key (shown only once).

### 3. Call It From Anywhere

**cURL:**
```bash
curl -X POST http://localhost:8000/api/v1/workflow-api/your-slug/execute \
  -H "X-API-Key: wfapi_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello from my app"}'
```

**JavaScript:**
```javascript
const response = await fetch('http://localhost:8000/api/v1/workflow-api/your-slug/execute', {
  method: 'POST',
  headers: {
    'X-API-Key': 'wfapi_your_key_here',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ input: 'Hello from my app' })
});
const data = await response.json();
console.log(data.output);
```

**Python:**
```python
import requests

response = requests.post(
    'http://localhost:8000/api/v1/workflow-api/your-slug/execute',
    headers={'X-API-Key': 'wfapi_your_key_here'},
    json={'input': 'Hello from my app'}
)
print(response.json()['output'])
```

### API Response Format
```json
{
  "success": true,
  "execution_id": "uuid",
  "status": "COMPLETED",
  "output": {
    "output_text": "AI generated response here",
    "model": "gemini-2.5-flash",
    "usage": { "input_tokens": 100, "output_tokens": 50 }
  },
  "usage": { "duration_ms": 2500 }
}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LITE_MODE` | `true` | `true` for single-process, `false` for Redis+Celery |
| `DATABASE_URL` | auto | PostgreSQL connection string |
| `JWT_SECRET` | auto-generated | Secret for JWT tokens |
| `ENCRYPTION_KEY` | auto-generated | Fernet key for encrypting secrets |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `GROQ_API_KEY` | — | Groq API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `REDIS_URL` | — | Redis URL (full mode only) |
| `CELERY_BROKER_URL` | — | Celery broker URL (full mode only) |
| `WEB_CONCURRENCY` | `1` | Number of uvicorn workers |

---

## Troubleshooting

### "Cannot connect to Docker daemon"
Start Docker Desktop and wait for the whale icon to appear in your menu bar.

### "Port 3000/8000 already in use"
Stop any other services on those ports, or change ports in the compose file.

### Platform won't start
```bash
fagoon logs -f     # Check logs for errors
fagoon down        # Stop everything
fagoon up          # Restart
```

### Reset everything
```bash
fagoon down
docker volume rm fagoon_db fagoon_data   # Removes all data
fagoon up
```

---

## Tech Stack

- **Backend:** Python, FastAPI, SQLAlchemy, PostgreSQL, pgvector
- **Frontend:** Next.js, React, TailwindCSS, React Flow
- **Workflow Engine:** Custom DAG executor with 20+ node types
- **Database:** PostgreSQL with pgvector for embeddings
- **Task Queue:** Celery + Redis (full mode)
- **Container:** Docker, Docker Compose

---

## License

MIT

---

## Links

- **Website:** [fagoonai.com](https://fagoonai.com)
- **GitHub:** [github.com/Fagoon-AI/upgrade](https://github.com/Fagoon-AI/upgrade)
- **PyPI:** [pypi.org/project/fagoon-upgrade](https://pypi.org/project/fagoon-upgrade)
