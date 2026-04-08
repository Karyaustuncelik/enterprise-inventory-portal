# Sanitization Checklist

## Scope
Public export refreshed from the current working backend and frontend sources.

## Kept
- Latest application source code for backend and frontend
- Generic environment examples
- Tests and migration scripts that do not disclose internal infrastructure

## Removed or replaced
- Company-branded logo assets and company-specific default domain values
- Internal deployment guides, IIS config files, and rollback material
- Internal hostnames, bindings, server names, and enterprise handover docs
- Build outputs, node modules, virtual environments, and packaging artifacts

## Public-safe replacements
- Neutral `Enterprise` brand asset
- Generic `ENTERPRISE` username domain default
- Generic local development API base (`http://localhost:8000`)
- Generic SQL Server environment placeholders

## Review rule
Before each future push, re-check for:
- hardcoded secrets
- internal hostnames
- company-specific branding
- rollback or deployment artifacts
- environment files
