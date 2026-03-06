# Enterprise Inventory Portal (Portfolio)

Sanitized portfolio version; no proprietary assets or secrets included.

## Tech Stack
**Frontend:** React 19, Vite 7, Axios, XLSX, plain CSS  
**Backend:** FastAPI, Pydantic, SQLite, header-based demo auth  
**DevOps/Tools:** Git

## Features
- Inventory CRUD operations
- Role-based user actions (Admin/Edit/View)
- Search and filtering on inventory rows
- Field parameter management
- Directory-style user lookup endpoint (demo data)
- Chart configuration CRUD
- Write-operation audit trail endpoint (`/audit-trail`)

## Repository Structure
- `frontend/` - Vite + React client
- `backend/` - FastAPI demo backend

## Setup
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

## GitHub Push Commands
```bash
git init
git add .
git commit -m "Initial public portfolio version"
git branch -M main
git remote add origin https://github.com/Karyaustuncelik/enterprise-inventory-portal.git
git push -u origin main
```

## Disclaimer
This repository is a sanitized portfolio edition for demonstration purposes.
Any confidential endpoints, internal infrastructure details, personal data, and credentials were removed or replaced.
