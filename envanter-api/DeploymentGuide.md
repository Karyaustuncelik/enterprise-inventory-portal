# Deployment Guide (FastAPI + SQL Server Behind IIS)

## Repository Drift Warning

Before packaging/deploying, verify these two points:

1. There are duplicate backend copies in this repository (`/` root and `/envanter-api`).
2. Those copies should be kept aligned so the deployment bundle does not accidentally ship stale files.

## 1. Prepare the Backend Package

Include these files/folders in the deployment bundle:

- `main.py`
- `database.py`
- `requirements.txt`
- `README.md`
- `DeploymentGuide.md`
- `tests/` (optional but recommended for reference)
- `web.config`

Recommended before zipping:

- Standardize the backend source you will deploy (prefer one source folder only).
- Confirm `database.py` is the intended environment-variable based version.

Create `enterprise-inventory-portal-api.zip` from the project root:

```powershell
Compress-Archive -Path main.py,database.py,requirements.txt,README.md,web.config,DeploymentGuide.md,tests `
                 -DestinationPath enterprise-inventory-portal-api.zip -Force
```

## 2. Server Prerequisites

1. Install Python 3.12 (64-bit) from python.org and ensure `py` and `python` are in PATH.
2. Install Microsoft ODBC Driver 17 or 18 for SQL Server.
3. In IIS, install Application Request Routing (ARR) and URL Rewrite modules (Web Platform Installer or manual MSIs).

## 3. Python Virtual Environment on IIS Host

```powershell
cd C:\EnterpriseInventoryPortal
py -3.12 -m venv venv
.\venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Keep the virtual environment inside the deployment directory (`C:\EnterpriseInventoryPortal\venv`) so it is isolated for the service user.

## 4. System-Level Environment Variables

Set the following (System Properties -> Environment Variables -> System):

```
DB_SERVER=YOUR_SQL_SERVER_NAME
DB_NAME=YOUR_DATABASE_NAME
DB_ENCRYPT=1
DB_TRUST_SERVER_CERTIFICATE=0
AUTH_WINDOWS_ENABLED=1
AUTH_TRUSTED_PROXY_IPS=127.0.0.1,::1
ADMIN_ROLE_IDS=1
LOG_LEVEL=INFO
```

Because the IIS worker uses Windows Authentication to SQL Server, **do not set** `DB_USER` or `DB_PASSWORD`; leaving them unset forces the connection to use `Trusted_Connection=yes` **when using the env-var based `database.py`**.  
Keep `DB_ENCRYPT=1` in production. Only set `DB_TRUST_SERVER_CERTIFICATE=1` when you intentionally accept the SQL Server certificate without chain validation.  
**Never** set `AUTH_FALLBACK_USERNAME`, `AUTH_FALLBACK_DISPLAY_NAME`, `DEV_AUTH_USERNAME`, or `DEV_AUTH_DISPLAY_NAME` in production; they bypass IIS authentication and are only for isolated local tests.

After adding or changing environment variables, restart the Uvicorn service so it picks up the new values (no full server reboot is required).

## 5. Create the Uvicorn Windows Service (NSSM)

1. Download NSSM (https://nssm.cc/).
2. Install the service (run PowerShell as Administrator):

```powershell
nssm install EnterpriseInventoryPortalAPI
```

3. In the NSSM GUI configure:
   - **Path:** `C:\EnterpriseInventoryPortal\venv\Scripts\uvicorn.exe`
   - **Arguments:** `main:app --host 127.0.0.1 --port 8000 --workers 4`
   - **Startup directory:** `C:\EnterpriseInventoryPortal`
   - **Environment:** add the same key/value pairs as in the system variables if you prefer service-level overrides.
4. Click *Install service*, then start it:

```powershell
nssm start EnterpriseInventoryPortalAPI
```

Confirm `netstat -ano | findstr 8000` shows the listener.

## 6. IIS Configuration

1. Open IIS Manager -> Sites -> *Add Website*.
   - Site name: `EnterpriseInventoryPortalAPI`
   - Physical path: `C:\EnterpriseInventoryPortal`
   - Binding: `https` on your desired port/hostname with the issued SSL certificate.
2. In the site -> Authentication:
   - Enable **Windows Authentication**
   - Disable **Anonymous Authentication**
3. Ensure ARR proxying is enabled: IIS root -> *Application Request Routing Cache* -> *Server Proxy Settings* -> Enable.
4. The provided `web.config` already contains the reverse-proxy rule that forwards requests to `http://127.0.0.1:8000` and injects `X-Remote-User`. The backend now trusts those identity headers only from `AUTH_TRUSTED_PROXY_IPS`, so keep the default loopback list unless your proxy sits on another IP.
5. Recycle the IIS site after changes.

Note: In some deployments, the frontend IIS application already proxies `/enterprise-inventory/api/*` to `127.0.0.1:8000`. In that topology, this backend `web.config` may be used only as a reference and not as the active reverse-proxy layer.

## 7. Testing

1. From a domain-joined workstation, browse to `https://SERVER/users/me`.
2. Expected responses:
   - If the logged-on Windows user exists in the SQL `UserRoles` table -> **200 OK** with user metadata.
   - If the user is missing from `UserRoles` -> **403 Forbidden**.
3. Check `C:\inetpub\logs\LogFiles` (IIS) and the Uvicorn service logs for troubleshooting (missing headers, SQL errors, etc.).

Once these steps succeed, the FastAPI backend runs behind IIS with Windows Authentication while Uvicorn handles the ASGI workload.
