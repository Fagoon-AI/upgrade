llm_model_configs migration

This folder contains SQL migrations for PostgreSQL. The repository currently does not include an Alembic configuration; migrations are applied manually by running the SQL against the database.

How to apply:

1. Ensure you have a working `DATABASE_URL` and the `users` table exists.
2. From the project root, run (example using psql):

```bash
psql "$DATABASE_URL" -f migrations/sql/20260610_create_llm_model_configs.sql
```

On some Postgres installations, `gen_random_uuid()` requires the `pgcrypto` extension; the migration enables it (`CREATE EXTENSION IF NOT EXISTS pgcrypto;`). If your environment restricts extensions, remove the `DEFAULT gen_random_uuid()` and generate UUIDs in the application layer.

Optional: Configure Alembic

To move to managed schema versioning, initialize Alembic and point `alembic.ini` and `env.py` at the SQLAlchemy metadata used in `src/models/sql`. Typical steps:

```bash
# in virtualenv
alembic init alembic
# edit alembic/env.py to use your SQLAlchemy Async engine and target_metadata
alembic revision --autogenerate -m "create llm_model_configs"
alembic upgrade head
```

If you want, I can scaffold an Alembic setup and generate a proper revision for this migration.