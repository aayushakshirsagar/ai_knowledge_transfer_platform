# Company Brain - AI Knowledge Transfer Platform

An AI-powered company knowledge management platform that captures, organizes, searches, and retrieves organizational knowledge using Retrieval-Augmented Generation (RAG).

---

# Project Status

**Current Phase:** Phase 0 - Project Foundation

Current Ticket:
- ✅ TICKET-001: Repository Setup, Environment Configuration & Local Development

---

# Tech Stack

## Backend

- Python 3.12
- FastAPI
- Pydantic
- uv (Package Manager)

## Infrastructure

- Docker
- Docker Compose
- PostgreSQL 16
- Redis 7
- Qdrant

## Planned

- Anthropic Claude
- Voyage AI Embeddings
- AWS S3
- Desktop Agent
- React Frontend

---

# Repository Structure

```
ai_knowledge_transfer_platform/

├── backend/
│   ├── app/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── uv.lock
│
├── desktop-agent/
│
├── frontend/
│
├── eval/
│
├── infra/
│   ├── docker-compose.yml
│   ├── .env.example
│   └── .env (local only)
│
├── scripts/
│
└── README.md
```

---

# Prerequisites

Install the following before running the project.

- Python 3.12+
- Git
- Docker Desktop
- uv

Install uv:

```
pip install uv
```

---

# Local Setup

## 1. Clone the repository

```
git clone <repository-url>
```

---

## 2. Open the backend folder

```
cd backend
```

---

## 3. Install dependencies

```
uv sync
```

---

## 4. Create environment file

Copy

```
infra/.env.example
```

to

```
infra/.env
```

Fill in the required values.

---

## 5. Start Docker

Open Docker Desktop and ensure the Docker Engine is running.

---

## 6. Start all services

From the `infra/` directory:

```
docker compose up --build
```

This starts:

- FastAPI Backend
- PostgreSQL 16
- Redis 7
- Qdrant

---

## 7. Verify services

Backend:

```
http://localhost:8000
```

Health Endpoint:

```
http://localhost:8000/health
```

Swagger Documentation:

```
http://localhost:8000/docs
```

Qdrant:

```
http://localhost:6333/dashboard
```

---

# Environment Variables

Environment variables are documented in

```
infra/.env.example
```

Do **NOT** commit

```
infra/.env
```

---

# Git Workflow

We follow a **ticket-based workflow**.

## Main Branch

The `main` branch should always remain stable and deployable.

Do not commit directly to `main`.

---

## Working on a Ticket

1. Pull the latest changes

```
git checkout main
git pull
```

2. Create a feature branch

```
git checkout -b feature/ticket-001-project-foundation
```

3. Complete the ticket.

4. Commit frequently with meaningful commit messages.

5. Push your branch.

6. Open a Pull Request.

7. Review and test.

8. Merge into `main`.

9. Delete the feature branch.

---

## Starting a New Ticket

Always begin from the latest `main`.

```
git checkout main
git pull
git checkout -b feature/ticket-002-<ticket-name>
```

---

# Team Workflow

- One feature branch per ticket.
- Multiple developers may work on the same ticket using separate branches if required.
- Merge only after testing.
- Delete branches after merging.
- Pull the latest `main` before starting every new ticket.

---

# GitHub Issues

GitHub Issues will be introduced as the project progresses.

Each Issue will represent a project ticket.

Future workflow:

Issue
↓

Feature Branch

↓

Pull Request

↓

Code Review

↓

Merge

↓

Close Issue

---

# Running the Backend Without Docker

From the backend folder:

```
uv run uvicorn app.main:app --reload
```

---

# Docker Commands

Start containers

```
docker compose up --build
```

Stop containers

```
docker compose down
```

View running containers

```
docker ps
```

View logs

```
docker compose logs
```

---

# Current Progress

- Repository initialized
- Monorepo structure created
- FastAPI project initialized
- Health endpoint implemented
- Configuration management using Pydantic Settings
- Dockerfile created
- Docker Compose configured
- PostgreSQL running
- Redis running
- Qdrant running
- Environment configuration completed

---

# Next Milestone

TICKET-002

Database models, SQLAlchemy, Alembic migrations, and initial persistence layer.

---

Maintainers

- Aayusha
- Project Team