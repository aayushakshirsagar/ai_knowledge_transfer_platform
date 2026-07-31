# Company Brain - Development Workflow

This document describes the day-to-day workflow for developing the Company Brain project.

---

# Project Structure

```
ai_knowledge_transfer_platform/

backend/
    FastAPI application
    Python code
    SQLAlchemy
    Alembic
    Tests

infra/
    Docker Compose
    Infrastructure
    Environment variables
```

---

# Before Starting Work

## 1. Start Docker Desktop

Always make sure Docker Desktop is running before working on the project.

Wait until Docker Desktop says it is running.

---

## 2. Open VS Code

Open the project folder.

---

## 3. Activate the Python Environment

Open a terminal inside the `backend` folder.

```
.\.venv\Scripts\Activate
```

Verify:

```
python --version
```

---

## 4. Start the Containers

Go to the `infra` folder.

```
cd infra
```

Start all services.

```
docker compose up -d
```

This starts:

- Backend
- PostgreSQL
- Redis
- Qdrant

---

## 5. Verify Containers

```
docker ps
```

Expected:

- company-brain-backend
- company-brain-postgres
- company-brain-redis
- company-brain-qdrant

---

# Development Workflow

## When writing Python code

Simply edit files inside VS Code.

No Docker rebuild is needed.

---

## When testing the API

Open

```
http://localhost:8000/health
```

Expected:

```json
{
  "status": "healthy"
}
```

---

## When running Alembic

The database lives inside Docker.

Run migrations from the backend container.

Example:

```
docker compose exec backend uv run alembic upgrade head
```

---

## When running tests

From the backend folder:

```
uv run pytest
```

---

## When checking formatting

```
uv run ruff check
```

---

## When installing a new dependency

Example:

```
uv add sqlalchemy
```

After installing dependencies:

Rebuild Docker.

```
docker compose up --build -d
```

---

# When Do I Need Docker?

Docker is required whenever my code needs:

- PostgreSQL
- Redis
- Qdrant
- FastAPI backend

If these services are needed, Docker must be running.

---

# When Do I NOT Need Docker?

Docker is not required for:

- Editing Python files
- Reading code
- Writing documentation
- Using Git
- Running Ruff
- Running local Python scripts that do not require the database

---

# When Do I Need To Rebuild?

Rebuild ONLY if one of these changes:

- Dockerfile
- pyproject.toml
- uv.lock
- Docker Compose configuration

Command:

```
docker compose up --build -d
```

---

# Normal Start Command

Every morning:

```
cd infra
docker compose up -d
```

---

# Normal Stop Command

When finished working:

```
docker compose down
```

---

# Git Workflow

## Before starting a ticket

```
git checkout main
git pull origin main
git checkout -b ticket-00X-description
```

---

## During development

Commit regularly.

```
git add .
git commit -m "Implement ticket XXX"
```

---

## Push

```
git push -u origin ticket-00X-description
```

---

## Create Pull Request

- Base: main
- Compare: ticket branch

Review changes before merging.

---

## After Merge

Switch back to main.

```
git checkout main
```

Update main.

```
git pull origin main
```

Delete the local branch.

```
git branch -d ticket-00X-description
```

Delete the remote branch (optional).

```
git push origin --delete ticket-00X-description
```

---

# Daily Checklist

Before coding:

- [ ] Docker Desktop running
- [ ] Python environment activated
- [ ] Containers started
- [ ] On correct Git branch
- [ ] Latest changes pulled from main

Before committing:

- [ ] Code runs
- [ ] Health endpoint works
- [ ] Tests pass (if applicable)
- [ ] Ruff passes
- [ ] No unnecessary files committed

Before opening a PR:

- [ ] Review all changed files
- [ ] Confirm only the intended ticket changes are included
- [ ] Write a clear PR description

After merging:

- [ ] Pull latest `main`
- [ ] Delete the completed feature branch
- [ ] Create a new branch for the next ticket