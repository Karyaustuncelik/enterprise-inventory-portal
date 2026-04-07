# Enterprise Inventory Portal Environment

## Important Repository State Note

This repository still contains duplicate backend copies (`/` root and `/envanter-api`), but the active `database.py` variants now use the same environment-variable based SQL configuration model. Keep deployment packages consistent so you do not accidentally ship stale copies of the backend.

Set the following environment variables on every host (local development, IIS worker, CI) before starting the FastAPI application:

```
DB_SERVER=YOUR_SQL_SERVER_NAME
DB_NAME=YOUR_DATABASE_NAME
DB_USER=YOUR_DB_USERNAME          # omit + rely on Trusted_Connection for integrated auth
DB_PASSWORD=YOUR_DB_PASSWORD       # omit when using integrated auth
DB_DRIVER=ODBC Driver 17 for SQL Server   # optional override, defaults to Driver 17
DB_ENCRYPT=1                      # default; keep enabled unless you fully understand the risk
DB_TRUST_SERVER_CERTIFICATE=0     # default; set to 1 only when you intentionally allow an untrusted SQL cert
AUTH_WINDOWS_ENABLED=1             # keep enabled behind IIS with Windows auth
AUTH_REMOTE_USER_HEADER=X-Remote-User   # optional override; default is X-Remote-User
AUTH_TRUSTED_PROXY_IPS=127.0.0.1,::1    # only these proxy/client IPs may supply remote-user headers
ADMIN_ROLE_IDS=1                   # comma-separated list of role ids treated as admins
DIRECTORY_SEARCH_ENABLED=0         # flip to 1 only if LDAP settings below are provided
DIRECTORY_SERVER=ldap://your-domain-controller
DIRECTORY_BASE_DN=DC=example,DC=com
DIRECTORY_BIND_USER=YOUR_LDAP_BIND_ACCOUNT
DIRECTORY_BIND_PASSWORD=YOUR_LDAP_BIND_PASSWORD
DIRECTORY_AUTH_TYPE=NTLM           # set to SIMPLE or other scheme as needed
DIRECTORY_INTEGRATED_AUTH=0        # set to 1 to use Kerberos integrated auth when bind credentials are omitted
DIRECTORY_USE_SSL=0                # set to 1 if LDAPS is required
DIRECTORY_SEARCH_SIZE=25
LOG_LEVEL=INFO
```

Directory auth modes:

- Explicit bind (recommended default): set `DIRECTORY_BIND_USER` + `DIRECTORY_BIND_PASSWORD`
- Integrated bind (passwordless): set `DIRECTORY_INTEGRATED_AUTH=1`, leave bind credentials empty, and run the backend process under a domain identity that has AD read permissions
- Integrated bind requires Kerberos runtime support in the Python environment (for example `winkerberos` on Windows hosts).

WARNING: never set `AUTH_FALLBACK_USERNAME`, `AUTH_FALLBACK_DISPLAY_NAME`, `DEV_AUTH_USERNAME`, or `DEV_AUTH_DISPLAY_NAME` in production. Those variables bypass IIS/Windows authentication and are strictly for isolated development environments when the reverse proxy cannot inject `REMOTE_USER`.

Security note: the backend now ignores `X-Remote-User` style headers unless the incoming client IP matches `AUTH_TRUSTED_PROXY_IPS`. The default loopback-only list is correct for IIS reverse-proxy deployments that forward traffic to `127.0.0.1:8000`.

All other application behavior (routes, SQL queries, etc.) depends on the values supplied here, so double-check the IIS worker process has read access to them (Machine-level environment variables or a secure secret source loaded by your process manager).
