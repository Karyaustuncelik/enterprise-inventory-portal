# Enterprise Inventory Portal - Backend

Sanitized portfolio backend with local SQLite demo mode and header-based demo authentication.

## Prerequisites
- Python 3.10+

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## Demo Authentication
- Default current user is `ENTERPRISE\admin` from `.env`.
- You can simulate another user with `X-Remote-User` header.
- `AUTH_AUTO_PROVISION=1` allows unknown users to be auto-created for demo usage.

## Local Database
- SQLite file: `data/demo.db`
- Seeded demo records are auto-created on first run.

## Key Endpoints
- `GET /health`
- `GET /rows`
- `POST /items`, `PUT /items/{item_ref}`, `DELETE /items/{item_ref}`
- `GET /users/me`, `GET /users`, `POST /users`, `PATCH /users/{id}`, `DELETE /users/{id}`
- `GET /field-parameters`, `POST/PUT/PATCH/DELETE` field parameter endpoints
- `GET /directory/search`, `GET /AutoSuggestName`
- `GET/POST/PUT/DELETE /charts`
- `GET /audit-trail`

## Notes
- This backend is sanitized for public portfolio use.
- No proprietary endpoints, hostnames, credentials, or private datasets are included.
