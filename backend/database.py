import os

import pyodbc

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _get_env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _build_connection_string() -> str:
    driver = (os.getenv("DB_DRIVER") or "ODBC Driver 17 for SQL Server").strip()
    user = (os.getenv("DB_USER") or "").strip()
    password = os.getenv("DB_PASSWORD") or ""
    encrypt = _get_env_bool("DB_ENCRYPT", True)
    trust_server_certificate = _get_env_bool("DB_TRUST_SERVER_CERTIFICATE", False)

    parts = [
        f"DRIVER={{{driver}}};",
        f"SERVER={_require_env('DB_SERVER')};",
        f"DATABASE={_require_env('DB_NAME')};",
        f"Encrypt={'yes' if encrypt else 'no'};",
        f"TrustServerCertificate={'yes' if trust_server_certificate else 'no'};",
    ]

    if user and password:
        parts.extend([f"UID={user};", f"PWD={password};"])
    elif user or password:
        raise RuntimeError("DB_USER and DB_PASSWORD must be set together.")
    else:
        parts.append("Trusted_Connection=yes;")

    return "".join(parts)


def get_conn():
    """Return a new pyodbc connection using environment-provided settings."""
    return pyodbc.connect(_build_connection_string())
