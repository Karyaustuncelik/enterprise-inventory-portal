# Sanitization Checklist

## Scope
- Source scanned from: `Frontend-copy/`, `Backend-copy/`
- Public output generated in: `enterprise-inventory-portal/frontend`, `enterprise-inventory-portal/backend`

## What Was Removed / Replaced
- Company-specific branding and references were replaced with neutral `Enterprise` naming.
- Proprietary logo/image assets were removed and replaced with a generic brand mark.
- Internal path/base URL defaults were replaced with local demo-safe defaults.
- Legacy IIS/deployment-specific config files were removed from public output.
- Backend was switched to a local SQLite demo mode with fake seeded data.

## Secret / Sensitive Handling
- No `.env` files copied.
- No hardcoded credentials, tokens, or production connection strings included.
- Runtime configuration moved to `.env.example` files.

## `.env.example` Files
- `frontend/.env.example`
- `backend/.env.example`

## Company-Specific Cleanup Areas
- Frontend header/loading branding and labels
- Frontend API defaults and storage keys
- Backend auth/database/deployment assumptions replaced by demo-safe alternatives
- Public docs/README rewritten as portfolio-safe

## Local Demo Mode
### Backend
- FastAPI + SQLite (`backend/data/demo.db`)
- Header-based demo identity (`X-Remote-User`) with safe fallback user
- Seeded with fake users/items/field parameters

### Frontend
- Vite dev server
- API base comes from `VITE_API_BASE` (default points to local backend)

## Notes
- This checklist intentionally avoids printing secret values.
- Optional/planned production integrations (SSO, enterprise DB, LDAP) are intentionally excluded from this public build.
