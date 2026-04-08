# Enterprise Inventory Portal - Frontend

Sanitized frontend source for the public portfolio repository.

## Stack
- React
- Vite
- Axios
- XLSX

## Setup
```bash
npm install
copy .env.example .env
npm run dev
```

## Build
```bash
npm run build
npm run preview
```

## Environment variables
- `VITE_API_BASE`: backend base URL, defaults to `http://localhost:8000`
- `VITE_API_WITH_CREDENTIALS`: `true` or `false`
- `VITE_REMOTE_USER`: optional demo/debug header override
- `VITE_AUTH_USERNAME_DOMAIN`: username domain prefix for user management flows

## Notes
- Company-branded assets were replaced with neutral branding.
- Internal IIS deployment files and handover docs are intentionally excluded.
