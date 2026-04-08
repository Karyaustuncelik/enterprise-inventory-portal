# Enterprise Inventory Portal (Public Sanitized Build)

Public-facing sanitized version of a full-stack inventory management portal. The project includes a React/Vite frontend and a FastAPI backend with advanced filtering, user and role management, configurable charts, and inventory workflows, while excluding internal deployment details, branded assets, and environment-specific infrastructure data.

## Highlights
- Full inventory CRUD flows with active and inactive inventory views
- Advanced table filtering, search tokenization, sorting, and export
- User, role, and field-parameter management screens
- Configurable charts and dashboard-style summaries
- SQL Server-ready backend configuration via environment variables
- Public-safe sanitized repository structure for portfolio and code review use

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
