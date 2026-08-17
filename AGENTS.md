# Repository Guidelines

## Project Structure & Module Organization

This repository contains the MONITOREO_SOPORTE backend and its operational agents.

- `backend/`: FastAPI API. Main entry points are `run.py` and `app/main.py`; routers live in `app/api/v1/`, business logic in `app/services/`, ORM models in `app/models/`, Pydantic schemas in `app/schemas/`, and infrastructure in `app/core/`.
- `agente/`: standalone Python 3.11 agent for SQL and Mongo backup validation on `10.0.3.8`.
- `agente_6_5/`: standalone Python 3.11 agent for Microsip and Mercaltos validation on `192.168.6.5`.
- `transfer/`: transfer worker and helper scripts for NAS-related workflows.
- `database/`: SQL Server schema and database documentation.

Keep shared agent files synchronized between `agente/` and `agente_6_5/`: `main.py`, `config.py`, `logger.py`, `api_client.py`, and `scripts/simular_respaldos.py`.

## Build, Test, and Development Commands

Backend setup and run:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python run.py
```

Open API docs at `http://localhost:8000/docs`; health check is `/api/v1/health`.

Agent simulation examples:

```powershell
cd agente
python scripts\simular_respaldos.py
python main.py --dry-run

cd ..\agente_6_5
python scripts\simular_respaldos.py
python main.py --fecha 2026-08-15 --dry-run
```

Utility scripts under `backend/scripts/` are executable with `python scripts\<name>.py`.

## Coding Style & Naming Conventions

Use Python 3.11+. Follow existing style: 4-space indentation, `snake_case` for functions, modules, variables, and script names; `PascalCase` for Pydantic and ORM classes. Keep FastAPI routers grouped by domain in `backend/app/api/v1/`. Prefer explicit, small service functions over placing business logic directly in route handlers.

## Testing Guidelines

There is no formal test runner configured yet. Current verification is script-based: use `backend/scripts/test_connection.py`, `backend/scripts/test_responsable_dia.py`, agent `--dry-run`, and simulator scripts. Name new verification scripts `test_<feature>.py` and keep them under the relevant `scripts/` folder unless a dedicated test suite is introduced.

## Commit & Pull Request Guidelines

Git history uses Conventional Commit style, usually Spanish descriptions, for example `feat(backup): agregar validación de respaldos de MongoDB`. Use `feat(scope): ...`, `fix(scope): ...`, or `chore(scope): ...` with concise imperative summaries.

Pull requests should describe the operational impact, list commands or scripts run, mention database changes, and call out `.env` or deployment requirements. Include screenshots only for UI-facing changes.

## Security & Configuration Tips

Never commit real `.env` files, API keys, SQL credentials, TLS private keys, or generated production data. Agent requests use `X-Agent-Key`; production `API_BASE_URL` values must use `https://`.
