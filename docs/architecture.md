# Project Architecture

## Project Name

`saas-starter-api` — Multi-tenant SaaS backend boilerplate.

## Folder Structure

```
saas-starter-api/
├── app/
│   ├── main.py
│   ├── routers/
│   ├── services/
│   ├── repositories/
│   ├── models/
│   ├── schemas/
│   ├── core/
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── redis.py
│   │   ├── auth.py
│   │   ├── exceptions.py
│   │   └── logging.py
│   └── workers/
│       └── celery_app.py
├── alembic/
│   └── versions/
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── integration/
├── .github/
│   └── workflows/
│       └── ci.yml
├── docker-compose.yml
├── pyproject.toml
├── alembic.ini
└── .env.example
```

## Layer Responsibilities

### `app/`
Python package root. Everything inside is your application. Files outside
(docker-compose.yml, pyproject.toml, etc.) are project tooling. Keeps the
app importable as a clean package and makes testing easier.

### `routers/`
Pure HTTP concerns only. Receives a request, validates the input shape,
calls a service, returns a response. No business logic, no queries.
If a router file grows past ~80 lines, business logic is likely leaking in.

### `services/`
Where "what does the app do" lives. A `UserService.register()` knows to
hash the password, check for duplicates, send a welcome email, and log the
event — but it has no idea how to run a SQL query. That separation is what
makes services unit-testable without a database.

### `repositories/`
All SQLAlchemy queries live here, nothing else (Repository Pattern).
If you ever switch databases, you only touch this layer. Services don't care.

### `models/`
SQLAlchemy ORM class definitions. Describes DB table shapes. No business
logic — just column definitions and relationships.

### `schemas/`
Pydantic models (DTOs). Describes API input/output shapes. Kept separate
from ORM models deliberately: `UserResponse` exposes `email` and
`created_at` but never `hashed_password`. Decouples API shape from DB shape.

### `core/`
Cross-cutting infrastructure every layer needs: DB session factory, Redis
client, JWT logic, config via Pydantic Settings, custom exceptions, logging.
Nothing domain-specific goes here.

### `workers/`
Celery task definitions. Separate so the worker container can be deployed
independently from the API container (different entrypoints, same codebase).

### `alembic/`
Migration history. Every schema change generates a versioned script here.
Think of it as `git` for your database schema.

### `tests/unit/`
Fast tests, no external dependencies. Services are tested here with mocked
repositories.

### `tests/integration/`
Slower tests that hit a real (test) database and Redis. Routers and
repository queries are tested here.

## Data Flow

```
HTTP Request
    ↓
routers/        ← validate input shape (Pydantic schema)
    ↓
services/       ← business logic, orchestration
    ↓
repositories/   ← SQL queries (SQLAlchemy)
    ↓
models/         ← ORM table definitions
    ↓
PostgreSQL
```

## Hard Rules

| Layer         | Can import             | Cannot import              |
|---------------|------------------------|----------------------------|
| routers       | services, schemas      | models, repositories, db   |
| services      | repositories, schemas  | SQLAlchemy session methods |
| repositories  | models, db session     | services, routers          |
| models        | SQLAlchemy base        | anything from app          |

## Key Concepts to Research

- **Repository Pattern** — why and when to use it
- **DTO (Data Transfer Object)** — the purpose of separating schemas from ORM models
- **PEP 517/518** — why `pyproject.toml` replaces `requirements.txt`
- **Dependency Injection in FastAPI** — how `Annotated[X, Depends(...)]` works
