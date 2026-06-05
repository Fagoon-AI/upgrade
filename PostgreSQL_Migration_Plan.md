# PostgreSQL Migration Plan: Fagoon AI Agents Workflow

## 1. Executive Summary
This document outlines the strategy for migrating the backend datastores from **MongoDB** (state, users, metadata) and **Qdrant** (vector search) to a unified **PostgreSQL** database using the **pgvector** extension. **Redis** will be retained exclusively as the task broker and result backend for Celery.

**Why this move?**
- **Unified Infrastructure:** Reduces the number of database services to manage from 3 to 2.
- **ACID Compliance:** Ensures absolute data integrity for user billing, chat histories, and agent configurations using relational constraints (Foreign Keys).
- **Simplified Local Dev:** Only PostgreSQL and Redis are needed to run the entire stack.

---

## 2. Architecture Changes

| Component | Current Tech | Target Tech |
| :--- | :--- | :--- |
| **Core Database** | MongoDB (Motor Async) | PostgreSQL (asyncpg / SQLAlchemy) |
| **Vector Database** | Qdrant | PostgreSQL (pgvector) |
| **Background Tasks** | Celery + Redis | Celery + Redis (No change) |
| **Migrations** | None (Schema-less) | Alembic (Schema versioning) |

---

## 3. Phased Implementation Plan

### Phase 1: Environment & Dependency Setup
1. **Dependencies:** Add `sqlalchemy`, `asyncpg`, `alembic`, and `pgvector` to Python dependencies.
2. **Infrastructure:** Update `docker-compose.yml` to replace the `qdrant` and `mongodb` services with a single `pgvector/pgvector:pg16` Docker image.
3. **Environment Variables:** Introduce `DATABASE_URL` for PostgreSQL and deprecate MongoDB/Qdrant URLs in `.env`.

### Phase 2: Schema Design (ORM)
PostgreSQL is strictly typed. We will create SQLAlchemy Declarative models (`src/models/sql/`) replacing the implicit BSON structures.
- **Core Entities:** `Users`, `GoogleTokens`, `Agents`, `AgentChatHistories`, `AgentChats`, `UpgradeChatHistories`, `UpgradeChats`.
- **Flexibility:** Use Postgres `JSONB` columns for unstructured metadata (e.g., `user_preferences`, flexible `Agent` configs).
- **Vector Entities:** Create a `DocumentChunks` table with a `Vector(1536)` column for embeddings (replacing Qdrant collections).

### Phase 3: Service Layer Refactoring
1. **Database Manager (`src/core/database/`):** Replace `MongoDBManager` with a `PostgresManager` that manages an async SQLAlchemy Engine and connection pool.
2. **Core Services (`src/services/sql/`):**
   - Create `PostgresServices` to replace `NoSqlServices`. Translate all `insert_data`, `find_one`, and `update_data` calls to SQLAlchemy async queries.
3. **Vector Storage (`src/storages/vectordb_storages/`):**
   - Create `PgVectorStorage` implementing the same interface as `QdrantStorage` (using `pgvector` cosine distance operators `<=>`).

### Phase 4: Application Integration & Dependency Injection
1. **Startup/Lifespan (`src/launch_server.py`):**
   - Swap MongoDB and Qdrant initializations with the new `PostgresManager` async engine startup.
2. **Global Dependencies (`src/core/globals.py`):**
   - Update the `get_nosql_services` dependency to `get_db_services`, injecting the new PostgreSQL session into FastAPI routers.
3. **Middleware (`AuthMiddleware`):** Update the authentication check to query the PostgreSQL `Users` and `RefreshTokens` tables.

### Phase 5: Celery Integration
- **`src/core/task_processing/celery_tasks.py`:** Update the Celery worker to instantiate its own synchronous (or async-wrapped) SQLAlchemy session to write video job statuses directly to the Postgres `VideoJobs` table. Redis remains fully responsible for queue management.

### Phase 6: Data Migration (ETL)
If existing data must be preserved:
1. **Script 1 (Mongo -> Postgres):** A Python script that connects to both databases, fetching users, agents, and chat history from Mongo and inserting them into the new Postgres schema.
2. **Script 2 (Qdrant -> Postgres):** A script that scrolls through Qdrant payloads and vectors and inserts them into the `DocumentChunks` table in Postgres.

### Phase 7: Testing and Deprecation
1. Run all unit/integration tests against the new PostgreSQL implementation.
2. Delete `mongodb.py`, `qdrant.py`, and remove Motor/Qdrant dependencies from `requirements.txt`/`pyproject.toml`.