# Alembic Setup Complete ✓

## What I've Done

1. ✅ Created `alembic.ini` — Alembic configuration
2. ✅ Created `alembic/env.py` — async migration environment with safe env defaults
3. ✅ Created `alembic/script.py.mako` — migration template
4. ✅ Generated first migration: `alembic/versions/a96116f90767_create_llm_model_configs.py`
5. ✅ Created `ALEMBIC_MIGRATION_GUIDE.md` — comprehensive guide
6. ✅ Created `alembic_helper.ps1` — convenient wrapper to avoid manual env var setup

---

## Quick Start: Apply Migration Now

### Option A: Using the helper script (Recommended)
```powershell
& .venv\Scripts\Activate.ps1
.\alembic_helper.ps1 upgrade head
```

### Option B: Manual env vars + alembic
```powershell
& .venv\Scripts\Activate.ps1

# Set env vars (paste the entire line)
$env:JWT_SECRET='alembic'; $env:JWT_ALGORITHM='HS256'; $env:GOOGLE_CLIENT_ID='alembic'; $env:GOOGLE_CLIENT_SECRET='alembic'; $env:GOOGLE_REDIRECT_URI='http://localhost'; $env:EMAIL_HOST='localhost'; $env:EMAIL_PORT='587'; $env:EMAIL_USERNAME='alembic'; $env:EMAIL_PASSWORD='alembic'; $env:EMAIL_FROM='alembic@test.com'; $env:GCS_BUCKET_NAME='alembic'; $env:GEMINI_API_KEY='alembic'; $env:VIDEO_STORAGE_PATH='/tmp'; $env:CELERY_BROKER_URL='redis://localhost'; $env:CELERY_RESULT_BACKEND='redis://localhost'; $env:SECRET_KEY='alembic'; $env:FAGOON_URL='http://localhost'; $env:DEFAULT_URL='http://localhost'; $env:SERPER_API_KEY='alembic'; $env:SERPAPI_API_KEY='alembic'; $env:COOKIE_DOMAIN_1='localhost'; $env:COOKIE_DOMAIN_2='localhost'; $env:COOKIE_DOMAIN_3='localhost'

# Run migration
alembic upgrade head
```

---

## What Gets Created

Running `alembic upgrade head` creates the `llm_model_configs` table with:
- `id` (UUID, primary key)
- `user_id` (UUID, foreign key → users.id)
- `name` (String)
- `provider` (String — "openai", "anthropic", "groq", "huggingface", "localhost")
- `model_id` (String, optional)
- `api_key` (Text, optional)
- `features` (JSONB list — ["chat", "agents", "workflow"])
- `agent_ids` (JSONB list)
- `workflow_ids` (JSONB list)
- `is_deleted` (Boolean, default=false)
- `created_at` (Timestamp)
- `updated_at` (Timestamp, auto-updates)

Index on `user_id` for fast queries.

---

## Next Steps

### Adding New Migrations
When you modify `src/models/sql/models.py`:
```powershell
.\alembic_helper.ps1 revision --autogenerate -m "your change description"
# Review alembic/versions/xyz_*.py
.\alembic_helper.ps1 upgrade head
```

### Migrating to a New Database (Full Copy)
```bash
# On source host
pg_dump -Fc -U user -d source_db -f backup.dump

# On target host
pg_restore -U user -d target_db backup.dump
```

The migration history is copied, so Alembic knows what's already applied!

### Migrating from Old DB to New DB (Schema Only)
```powershell
.\alembic_helper.ps1 upgrade head
```

---

## Key Files

| File | Purpose |
|------|---------|
| `alembic.ini` | Alembic config |
| `alembic/env.py` | Migration environment (reads models from SQLAlchemy) |
| `alembic/versions/` | All migration scripts live here |
| `alembic_helper.ps1` | Convenient wrapper (PowerShell) |
| `ALEMBIC_MIGRATION_GUIDE.md` | Full documentation |

---

## Troubleshooting

**Error: "No such file or directory: alembic\script.py.mako"**
→ Fixed! Created the template.

**Error: Settings import failed / Missing env vars**
→ Use `alembic_helper.ps1` which sets safe defaults, or manually set env vars (see Quick Start above).

**Migration succeeded but table doesn't exist in DB**
→ Run `alembic current` to check version; may need `alembic upgrade head` or verify DB connection.

**Want to rollback?**
```powershell
.\alembic_helper.ps1 downgrade -1
```

---

## Questions?

See `ALEMBIC_MIGRATION_GUIDE.md` for comprehensive docs on:
- Using Alembic commands
- Creating migrations
- Database transfers (pg_dump, ETL, etc.)
- CI/CD integration
- Troubleshooting
