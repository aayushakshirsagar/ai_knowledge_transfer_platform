## updated till tickets 001-003 

## setup 

1. Create an environment / update an environment 
- cd backend
- uv sync

2. Start Docker Infrastructure

- cd infra 
- docker compose up --build -d / docker compose up -d ( when nothing is new )
- docker ps - verify the containers 

Expected containers:

```
company-brain-backend
company-brain-postgres
company-brain-redis
company-brain-qdrant
```

---

 You can do additional checks for all containers

 Redis
- docker exec -it company-brain-redis redis-cli
- enter  PING

Qdrant 
- http://localhost:6333/dashboard



3. Verify the Backend 

Health endpoint

```
http://localhost:8000/health
```

Swagger

```
http://localhost:8000/docs
```

Expected health response

```json
{
    "status": "ok"
}
```

---
Always use

```bash
uv run
```

instead of activating the virtual environment.

4. To setup the backend 

- cd backend 
- uv run alembic upgrade head 

verify it by 
- cd infra 
- docker exec -it company-brain-postgres psql -U postgres

- \c company_brain - connects postgres to the database 

- \dt

- SELECT * FROM alembic_version;

5.Ticket 003 - just Vector Store code 

- cd backend 
- uv run pytest tests/test_vector_store.py -v

## Summary 
Ticket 001 - docker compose up -d 
Tikcet 002 - uv run alembic upgrade head 
Ticket 003 - uv run pytest tests/test_vector_store.py -v 

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
