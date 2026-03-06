# Enterprise Inventory Portal - Frontend

Sanitized portfolio frontend for the inventory portal.

## Prerequisites
- Node.js 20+
- npm 10+

## Setup
```bash
npm install
cp .env.example .env
npm run dev
```

## Build
```bash
npm run build
npm run preview
```

## Environment Variables
- `VITE_API_BASE`: Backend base URL (default in demo: `http://localhost:8000`)
- `VITE_API_WITH_CREDENTIALS`: `true`/`false`
- `VITE_REMOTE_USER`: Optional demo user header
- `VITE_AUTH_USERNAME_DOMAIN`: Domain prefix used when adding users

## Notes
- This is a sanitized portfolio version.
- No proprietary assets, hostnames, or secrets are included.
