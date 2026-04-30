# Scaffold Design — saas-starter-api

**Date:** 2026-04-30
**Scope:** Step 1 — project scaffold, folder structure, Docker Compose, DB + Redis setup

---

## Project Name

`saas-starter-api` — descriptive, searchable, honest about its purpose as a portfolio boilerplate.

---

## Architecture

Layered architecture, strictly enforced top-to-bottom:

```
routers → services → repositories → models
```

- Routers handle HTTP only (parse request, call service, return schema).
- Services own all business logic; they are HTTP-unaware.
- Repositories own all SQLAlchemy queries; services never write SQL.
- Models are ORM-only; they are never sent over the wire.
- Schemas (Pydantic v2) are the API contract; they never import ORM models.

---

## Folder Structure

```
saas-starter-api/
├── app/
│   ├── main.py                  # FastAPI app factory
│   ├── routers/
│   │   └── v1/                  # versioned from day one
│   │       ├── auth.py
│   │       ├── users.py
│   │       └── workspaces.py
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── user_service.py
│   │   └── workspace_service.py
│   ├── repositories/
│   │   ├── user_repo.py
│   │   └── workspace_repo.py
│   ├── models/
│   │   ├── base.py              # DeclarativeBase
│   │   ├── user.py
│   │   └── workspace.py
│   ├── schemas/
│   │   ├── auth.py              # token request/response DTOs
│   │   ├── user.py
│   │   └── workspace.py
│   ├── core/
│   │   ├── config.py            # Pydantic Settings + .env loading
│   │   ├── db.py                # async SQLAlchemy engine + session factory
│   │   ├── redis.py             # Redis client
│   │   ├── auth.py              # JWT helpers, password hashing
│   │   ├── deps.py              # FastAPI Depends() factories
│   │   └── exceptions.py        # AppError base + HTTP exception handlers
│   └── workers/
│       ├── celery_app.py        # Celery app factory
│       ├── email.py
│       └── reports.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── integration/
├── alembic/
│   └── versions/
├── .github/
│   └── workflows/
│       └── ci.yml
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env.example
└── .gitignore
```

---

## Key Decisions

| Decision | Choice | Reason |
|---|---|---|
| Structure style | Layer-first (Approach A) | Makes architecture visible to portfolio reviewers instantly |
| API versioning | `routers/v1/` from day one | Allows future `v2/` without touching service/repo code |
| Dependency management | `pyproject.toml` | Modern PEP 517/518 standard; replaces requirements.txt + setup.py |
| Branch strategy | `feature/* → develop → main` | `main` stays always-deployable; `develop` integrates features |

---

## Git Setup

```bash
git checkout -b develop
mkdir -p app/routers/v1 app/services app/repositories app/models app/schemas \
         app/core app/workers \
         tests/unit tests/integration \
         alembic/versions \
         .github/workflows
find app tests alembic .github -type d -exec touch {}/.gitkeep \;
touch app/__init__.py app/main.py \
      alembic.ini docker-compose.yml Dockerfile pyproject.toml .env.example .gitignore
git add .
git commit -m "chore(scaffold): initialize project structure"
```

---

## Out of Scope (handled in later steps)

- Docker Compose service definitions (Step 1 implementation)
- Alembic env.py configuration (Step 1 implementation)
- User auth implementation (Step 2)
- Multi-tenancy strategy decision (Step 3)
- RBAC, Stripe, Celery tasks (Steps 4–7)
