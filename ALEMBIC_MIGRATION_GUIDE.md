# Alembic Migration Guide for Fagoon AI Agents Workflow

## Quick Reference

### Setup & Prerequisites
```bash
# Activate virtualenv (PowerShell)
& .venv\Scripts\Activate.ps1

# Set required env vars (PowerShell one-liner for migrations)
$env:JWT_SECRET='alembic'; $env:JWT_ALGORITHM='HS256'; $env:GOOGLE_CLIENT_ID='alembic'; $env:GOOGLE_CLIENT_SECRET='alembic'; $env:GOOGLE_REDIRECT_URI='http://localhost'; $env:EMAIL_HOST='localhost'; $env:EMAIL_PORT='587'; $env:EMAIL_USERNAME='alembic'; $env:EMAIL_PASSWORD='alembic'; $env:EMAIL_FROM='alembic@test.com'; $env:GCS_BUCKET_NAME='alembic'; $env:GEMINI_API_KEY='alembic'; $env:VIDEO_STORAGE_PATH='/tmp'; $env:CELERY_BROKER_URL='redis://localhost'; $env:CELERY_RESULT_BACKEND='redis://localhost'; $env:SECRET_KEY='alembic'; $env:FAGOON_URL='http://localhost'; $env:DEFAULT_URL='http://localhost'; $env:SERPER_API_KEY='alembic'; $env:SERPAPI_API_KEY='alembic'; $env:COOKIE_DOMAIN_1='localhost'; $env:COOKIE_DOMAIN_2='localhost'; $env:COOKIE_DOMAIN_3='localhost'
```

### Common Alembic Commands

**Apply all pending migrations to the database:**
```bash
alembic upgrade head
```

**Apply one migration step:**
```bash
alembic upgrade +1
```

**Revert one migration step:**
```bash
alembic downgrade -1
```

**View current migration status:**
```bash
alembic current
```

**View migration history:**
```bash
alembic history --verbose
```

**Generate a new migration from model changes:**
```bash
alembic revision --autogenerate -m "your descriptive message"
```

---

## Part 1: Applying Migrations to Your Current Database

### Step 1: Prepare Environment
Ensure your `.env` file has `DATABASE_URL` set to your current Postgres instance:
```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/fagoon_db
```

### Step 2: Apply Migration
```bash
alembic upgrade head
```

This will:
1. Check the `alembic_version` table in your DB
2. Detect pending migrations (revisions not yet applied)
3. Run `upgrade()` for each pending migration
4. Update `alembic_version` table

**Result:** The `llm_model_configs` table is now created in your database.

### Step 3: Verify
```bash
# Check if migration was applied
alembic current

# Or query the database directly
psql "$DATABASE_URL" -c "\dt llm_model_configs"
```

---

## Part 2: Creating Future Migrations

When you add or modify SQLAlchemy models in `src/models/sql/models.py`:

### Option A: Autogenerate (Automatic)
```bash
# Set env vars (see Quick Reference above)
alembic revision --autogenerate -m "descriptive change message"
```

This compares your SQLAlchemy models to the current DB schema and generates DDL automatically.

**Always review the generated file!** Autogenerate is not perfect and may need manual edits.

### Option B: Manual (Full Control)
```bash
alembic revision -m "descriptive change message"
```

Then edit the generated file in `alembic/versions/` and write the `upgrade()` and `downgrade()` functions using Alembic operations:

```python
def upgrade() -> None:
    op.add_column('table_name', sa.Column('new_column', sa.String(100)))

def downgrade() -> None:
    op.drop_column('table_name', 'new_column')
```

**Common Alembic operations:**
- `op.create_table(...)` — create a new table
- `op.drop_table(...)` — drop a table
- `op.add_column(...)` — add a column
- `op.drop_column(...)` — remove a column
- `op.alter_column(...)` — modify a column
- `op.create_index(...)` — add an index
- `op.drop_index(...)` — remove an index
- `op.execute(sql)` — run raw SQL

---

## Part 3: Migrating to a New Database (Full Schema + Data Transfer)

### Scenario: You want to move from PostgreSQL A to PostgreSQL B

#### Option 1: Using `pg_dump` & `pg_restore` (Recommended for Full DB)

This is the fastest and most reliable way to copy an entire PostgreSQL database:

**On source database host:**
```bash
# Dump the entire database (custom binary format, fastest)
pg_dump -Fc -h src_host -U src_user -d src_database_name -f dump.dump

# Or dump as SQL script (human-readable)
pg_dump -h src_host -U src_user -d src_database_name -f dump.sql
```

**Transfer dump file to target host (scp, S3, etc.)**

**On target database host:**
```bash
# Restore from dump
pg_restore -h target_host -U target_user -d target_database_name -c dump.dump

# If restoring SQL script:
psql -h target_host -U target_user -d target_database_name < dump.sql
```

**Alembic integration:** No action needed! `alembic_version` table is copied, so Alembic knows which migrations have been applied.

#### Option 2: Using Alembic Only (Schema Only, No Data)

If you only need the schema (not existing data):

**On target database:**
```bash
# Ensure database is empty or drop/recreate it
dropdb -h target_host -U target_user target_database_name
createdb -h target_host -U target_user -E UTF8 target_database_name

# Run all migrations
alembic upgrade head
```

#### Option 3: ETL Script (Custom Data Transform)

If you're migrating from a different database engine (e.g., MongoDB→PostgreSQL) or need to transform data:

**Create a migration script:**

```python
# alembic/versions/migrate_data_from_mongo.py
"""Migrate user data from MongoDB to PostgreSQL

Revision ID: xyz123
Revises: previous_revision
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


def upgrade() -> None:
    """
    Example: Populate llm_model_configs for existing users with default config
    """
    conn = op.get_bind()
    
    # If you have a MongoDB source, you'd read from it here and insert
    # For now, example creates default entries for all users:
    query = text("""
        INSERT INTO llm_model_configs (id, user_id, name, provider, model_id, api_key, features, created_at, updated_at)
        SELECT 
            gen_random_uuid(),
            id,
            'Default OpenAI',
            'openai',
            'gpt-4o',
            '',
            '["chat", "agents"]'::jsonb,
            now(),
            now()
        FROM users
        WHERE id NOT IN (SELECT DISTINCT user_id FROM llm_model_configs)
    """)
    conn.execute(query)


def downgrade() -> None:
    """Remove auto-populated entries"""
    conn = op.get_bind()
    conn.execute(text("DELETE FROM llm_model_configs WHERE api_key = '';"))
```

---

## Part 4: Handling Schema Drift

If your database schema doesn't match Alembic's expectations:

### Issue: Alembic says "target database is not up to date"

**Solution: Stamp the current state**
```bash
# Tell Alembic: "The current database schema IS revision HEAD"
alembic stamp head
```

Use this carefully! Only use if you've manually created tables or know they match the models.

### Issue: You need to reset and start fresh

```bash
# Drop all tables
dropdb -h host -U user database_name
createdb -h host -U user -E UTF8 database_name

# Remove alembic version tracking (Alembic will recreate the table)
# Then run migrations
alembic upgrade head
```

---

## Part 5: Environment Variables for CI/CD

If running Alembic in CI/CD (GitHub Actions, GitLab CI, etc.), set these before running Alembic:

**GitHub Actions example:**
```yaml
- name: Run Alembic Migrations
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
    JWT_SECRET: ${{ secrets.JWT_SECRET }}
    GOOGLE_CLIENT_ID: ${{ secrets.GOOGLE_CLIENT_ID }}
    GOOGLE_CLIENT_SECRET: ${{ secrets.GOOGLE_CLIENT_SECRET }}
    # ... other required env vars
  run: |
    alembic upgrade head
```

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `ModuleNotFoundError: No module named 'src'` | Python path not set | Run Alembic from project root; ensure `alembic/env.py` has `sys.path.insert(0, ...)` |
| Settings import error | Missing env vars | Set all required env vars before running Alembic (see Quick Reference) |
| `No such table: alembic_version` | First time running Alembic | Just run `alembic upgrade head` — it will create the table |
| Autogenerate produces empty migration | No differences detected | Manually edit the migration file or check if DB already matches models |
| Downgrade fails | Missing `downgrade()` implementation | Edit the migration file and add proper rollback DDL |

---

## Example: Full Workflow

**Day 1: Add a new feature column**
```python
# 1. Edit src/models/sql/models.py
class LLMModelConfig(Base):
    ...
    custom_param: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

# 2. Generate migration
$ alembic revision --autogenerate -m "add custom_param to llm_model_configs"

# 3. Review alembic/versions/xyz_add_custom_param.py

# 4. Apply migration
$ alembic upgrade head

# 5. Deploy and done!
```

**Day 2: Migrate to new database**
```bash
# On old DB host
$ pg_dump -Fc -U user -d fagoon_db > /tmp/backup.dump

# Transfer backup.dump to new server, then:
$ pg_restore -U user -d fagoon_db_new /tmp/backup.dump

# Done! New DB has schema + data + migration history
```

---

## References

- [Alembic Docs](https://alembic.sqlalchemy.org/)
- [SQLAlchemy ORM Declarative](https://docs.sqlalchemy.org/en/20/orm/declarative.html)
- [PostgreSQL pg_dump docs](https://www.postgresql.org/docs/current/app-pgdump.html)
