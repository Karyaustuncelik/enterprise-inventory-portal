# Enterprise Inventory Portal - Backend

Sanitized backend source for the public portfolio repository.

## Stack
- FastAPI
- Pydantic
- pyodbc
- ldap3 (optional)

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## Configuration model
- Database access is fully environment-driven.
- SQL Server connection settings come from `.env` / process environment.
- Optional directory lookup is disabled unless its env vars are supplied.
- Reverse-proxy / SSO deployment specifics are intentionally not included in this public repo.

## Included
- API source (`main.py`, `database.py`)
- migration scripts
- test files covering auth hardening, chart behavior, defaults, and filtering

## Excluded
- IIS deployment files
- internal infrastructure documentation
- rollback scripts and server-specific settings
