# Ticket 002 — Database Schema, ORM Models, Alembic, Seed Data

## Purpose

This ticket implements the backend persistence layer for Company Brain:

- SQLAlchemy 2.0 ORM models for the core project schema
- Alembic migrations for database versioning
- a seed script that creates demo data:
  - one project
  - two users
  - one project assignment

The goal is to make the database schema reproducible and easy for coworkers to run locally.

## What is included

- `backend/app/models/base.py`
- `backend/app/models/tables.py`
- `backend/app/db/session.py`
- `backend/app/db/migrations/env.py`
- `backend/app/db/migrations/versions/0001_initial.py`
- `backend/alembic.ini`
- `scripts/seed_projects.py`

## Prerequisites

- Python 3.12+
- Docker Desktop (for local Postgres)
- uv package manager
- `infra/.env` copied from `infra/.env.example`

## Setup

### 1. Start Postgres

From `infra/`:

```powershell
cd "c:\Users\aayus\OneDrive\Desktop\companies brain project\ai_knowledge_transfer_platform\infra"
docker compose up -d postgres
```

If you want the full stack, use:

```powershell
docker compose up -d
```

### 2. Create or recreate the backend virtual environment

From `backend/`:

```powershell
cd "c:\Users\aayus\OneDrive\Desktop\companies brain project\ai_knowledge_transfer_platform\backend"
python -m venv .venv
```

### 3. Activate the backend venv

```powershell
.\.venv\Scripts\Activate.ps1
```

### 4. Install `uv` and sync dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install uv
uv sync
```

### 5. Set the database URL

From either the repo root or `backend/`:

```powershell
$env:DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/company_brain"
```

If you prefer, add the same database URL to `infra/.env` and make sure `backend/app/core/settings.py` can read it.

## Run migrations

From `backend/`:

```powershell
uv run alembic upgrade head
```

If `uv` is not available or the environment is broken, use:

```powershell
python -m alembic upgrade head
```

## Seed demo data

From the repo root:

```powershell
cd "c:\Users\aayus\OneDrive\Desktop\companies brain project\ai_knowledge_transfer_platform"
uv run python scripts/seed_projects.py
```

If working from `backend/`:

```powershell
uv run python ..\scripts\seed_projects.py
```

Expected output:

```text
Seeded demo project 1 and users 1, 2
```

## Verify the seeded data in Postgres

### Option 1: `psql`

```powershell
psql -h localhost -U postgres -d company_brain
```

Then run:

```sql
SELECT * FROM users;
SELECT * FROM projects;
SELECT * FROM project_assignments;
```

### Option 2: Docker Postgres

From `infra/`:

```powershell
docker compose exec postgres psql -U postgres -d company_brain
```

Then run the same SQL.

### Expected seed rows

- `users` contains `demo.user@company.com` and `admin.user@company.com`
- `projects` contains `Demo Project`
- `project_assignments` links `project_id = 1` to `user_id = 1` with `assigned_by = 2`

## Troubleshooting

- If `uv run` fails and the venv is broken, recreate `.venv`.
- If `python -m alembic` reports `No module named alembic`, install Alembic into the active venv.
- If `scripts/seed_projects.py` reports `ModuleNotFoundError: app`, confirm `scripts/seed_projects.py` includes:

```python
ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parent / "backend"
sys.path.insert(0, str(BACKEND))
```

- If the `projects` query output shows `END`, that is just the `psql` pager indicating the end of output.

## Notes

- This README is specific to Ticket 002.
- Do not commit `infra/.env`.
- Use the same `DATABASE_URL` that is configured in the backend.
- The seed script uses `Base.metadata.create_all(...)` for convenience, but production should use Alembic migrations.
