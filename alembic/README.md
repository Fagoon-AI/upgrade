Alembic usage for this repository

This project uses SQLAlchemy 2.x with async engines. Alembic is configured to use the `system_setting.DATABASE_URL` from `src.core.settings` when running migrations from the project root.

Quick start:

1. Ensure your virtualenv is activated and `DATABASE_URL` is set in your environment (or in `.env` if you load it).

2. To create a new revision (autogenerate):

```bash
alembic revision --autogenerate -m "describe change"
```

3. To apply migrations:

```bash
alembic upgrade head
```

Notes:
- The `alembic/env.py` imports `src.models.sql.base.Base` to get `target_metadata` for autogeneration.
- If you run Alembic from outside the project root, ensure Python path includes the project directory so `src` can be imported.
- For CI or production, set `DATABASE_URL` in the environment prior to running Alembic commands.

If you'd like, I can generate an initial revision file for the existing models (creates schema for all tables currently defined in `src/models/sql/models.py`).