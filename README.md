# Enterprise Inventory Portal (Public Sanitized Build)

Public-facing sanitized repository for the inventory portal. This edition keeps the application code, removes proprietary branding and deployment details, and avoids shipping internal infrastructure information.

## Structure
- `backend/` FastAPI backend
- `frontend/` React + Vite frontend

## What is intentionally excluded
- Production IIS / reverse-proxy configuration
- Internal hostnames, bindings, and deployment paths
- Company-branded assets
- Environment-specific credentials and rollback artifacts
- Internal technical handover documents

## Local setup
### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend
```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

## Notes
- The backend expects a SQL Server database configured through environment variables.
- Optional directory lookup support is environment-driven and disabled by default unless configured.
- This repository is intended for portfolio / code-review use, not as a production deployment package.
