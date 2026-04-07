# main.py

import logging
import os
import ipaddress
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from database import get_conn

app = FastAPI(title="Enterprise Inventory Portal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("enterprise_inventory_portal.api")


@app.on_event("startup")
async def log_database_target() -> None:
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT DB_NAME() AS DatabaseName, @@SERVERNAME AS ServerName")
        row = cursor.fetchone()
        if row:
            db_name = row[0]
            server_name = row[1]
            logger.info("Database target: SERVER=%s;DATABASE=%s", server_name, db_name)
        else:
            logger.info("Database target: unknown (no rows returned).")
    except Exception as exc:
        logger.warning("Failed to read database target: %s", exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _get_env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value.strip())
    except ValueError:
        logger.warning("Invalid int value for %s: %s. Falling back to %s.", name, value, default)
        return default


def _parse_admin_role_ids(value: Optional[str]) -> Tuple[int, ...]:
    if not value:
        return (1,)
    result: List[int] = []
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            result.append(int(raw))
        except ValueError:
            logger.warning("Skipping invalid ADMIN_ROLE_IDS entry: %s", raw)
    return tuple(result) or (1,)


def _parse_csv_values(value: Optional[str], default: Tuple[str, ...]) -> Tuple[str, ...]:
    if not value:
        return default
    values = tuple(part.strip() for part in value.split(",") if part.strip())
    return values or default


@dataclass
class AuthSettings:
    windows_auth_enabled: bool = True
    remote_user_header: str = "X-Remote-User"
    trusted_proxy_ips: Tuple[str, ...] = ("127.0.0.1", "::1")
    fallback_username: Optional[str] = None
    fallback_display_name: Optional[str] = None
    directory_enabled: bool = False
    directory_server: Optional[str] = None
    directory_user: Optional[str] = None
    directory_password: Optional[str] = None
    directory_base_dn: Optional[str] = None
    directory_auth_type: str = "NTLM"
    directory_integrated_auth: bool = False
    directory_use_ssl: bool = False
    directory_search_size: int = 25
    admin_role_ids: Tuple[int, ...] = (1,)


@dataclass(frozen=True)
class DirectoryUserData:
    username: str
    display_name: Optional[str]
    email: Optional[str]


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    return AuthSettings(
        windows_auth_enabled=_get_env_bool("AUTH_WINDOWS_ENABLED", True),
        remote_user_header=os.getenv("AUTH_REMOTE_USER_HEADER", "X-Remote-User"),
        trusted_proxy_ips=_parse_csv_values(os.getenv("AUTH_TRUSTED_PROXY_IPS"), ("127.0.0.1", "::1")),
        fallback_username=os.getenv("AUTH_FALLBACK_USERNAME") or os.getenv("DEV_AUTH_USERNAME"),
        fallback_display_name=os.getenv("AUTH_FALLBACK_DISPLAY_NAME") or os.getenv("DEV_AUTH_DISPLAY_NAME"),
        directory_enabled=_get_env_bool("DIRECTORY_SEARCH_ENABLED", False),
        directory_server=os.getenv("DIRECTORY_SERVER"),
        directory_user=os.getenv("DIRECTORY_BIND_USER"),
        directory_password=os.getenv("DIRECTORY_BIND_PASSWORD"),
        directory_base_dn=os.getenv("DIRECTORY_BASE_DN"),
        directory_auth_type=os.getenv("DIRECTORY_AUTH_TYPE", "NTLM"),
        directory_integrated_auth=_get_env_bool("DIRECTORY_INTEGRATED_AUTH", False),
        directory_use_ssl=_get_env_bool("DIRECTORY_USE_SSL", False),
        directory_search_size=_get_env_int("DIRECTORY_SEARCH_SIZE", 25),
        admin_role_ids=_parse_admin_role_ids(os.getenv("ADMIN_ROLE_IDS")),
    )


def to_camel(string: str) -> str:
    parts = string.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


@dataclass
class UserRecord:
    id: Optional[int]
    username: str
    display_name: Optional[str]
    role_id: Optional[int]
    role_name: Optional[str]

    @property
    def is_admin(self) -> bool:
        role_name = (self.role_name or "").strip().lower()
        return (self.role_id in get_auth_settings().admin_role_ids) or role_name == "admin"


def _normalise_username(username: str) -> str:
    return username.strip()


def _normalise_userroles_username(username: str) -> str:
    raw = _normalise_username(username)
    if not raw:
        return raw
    if "\\" in raw:
        return raw
    short_username = _normalise_auth_username(raw) or raw
    domain = (os.getenv("AUTH_USERNAME_DOMAIN") or "EXAMPLE").strip()
    if not domain:
        return short_username
    return f"{domain}\\{short_username}"


def _normalise_auth_username(username: str) -> str:
    candidate = (username or "").strip()
    if not candidate:
        return ""
    if "\\" in candidate:
        candidate = candidate.split("\\")[-1]
    if "@" in candidate:
        candidate = candidate.split("@")[0]
    return candidate.strip()


def _username_short_sql(column_sql: str) -> str:
    trimmed = f"LTRIM(RTRIM({column_sql}))"
    return (
        "CASE "
        f"WHEN CHARINDEX('\\', {trimmed}) > 0 THEN RIGHT({trimmed}, LEN({trimmed}) - CHARINDEX('\\', {trimmed})) "
        f"WHEN CHARINDEX('@', {trimmed}) > 0 THEN LEFT({trimmed}, CHARINDEX('@', {trimmed}) - 1) "
        f"ELSE {trimmed} "
        "END"
    )


def _derive_display_name_from_username(username: str) -> str:
    if not username:
        return ""
    candidate = username.split("\\")[-1]
    candidate = candidate.replace(".", " ")
    parts = [part for part in candidate.split() if part]
    if not parts:
        return candidate.title()
    return " ".join(part.capitalize() for part in parts)


def _escape_ldap_value(value: str) -> str:
    replacements = {
        "\\": r"\5c",
        "*": r"\2a",
        "(": r"\28",
        ")": r"\29",
        "\0": r"\00",
    }
    escaped = []
    for char in value:
        escaped.append(replacements.get(char, char))
    return "".join(escaped)


def _normalise_directory_query(query: str) -> str:
    candidate = (query or "").strip()
    if not candidate:
        return ""
    # UI placeholder suggests DOMAIN\username; AD search fields usually store only the username part.
    if "\\" in candidate:
        candidate = candidate.split("\\")[-1]
    return candidate.strip()


def _create_directory_connection(settings: AuthSettings):
    try:
        from ldap3 import ALL, Connection, KERBEROS, NTLM, SASL, Server
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning("ldap3 package not installed. Directory lookup disabled.")
        return None

    if not settings.directory_server or not settings.directory_base_dn:
        return None

    server = Server(
        settings.directory_server,
        use_ssl=settings.directory_use_ssl,
        get_info=ALL,
    )

    has_bind_credentials = bool(settings.directory_user and settings.directory_password)
    bind_mode = "credentials"

    if has_bind_credentials:
        auth_type = settings.directory_auth_type.upper()
        conn = Connection(
            server,
            user=settings.directory_user,
            password=settings.directory_password,
            authentication=NTLM if auth_type == "NTLM" else auth_type,
            receive_timeout=10.0,
        )
    elif settings.directory_integrated_auth:
        # Kerberos integrated auth uses the process identity and does not require LDAP secrets.
        bind_mode = "integrated"
        conn = Connection(
            server,
            authentication=SASL,
            sasl_mechanism=KERBEROS,
            receive_timeout=10.0,
        )
    else:
        logger.warning(
            "Directory lookup is enabled but no bind credentials are configured. "
            "Set DIRECTORY_BIND_USER and DIRECTORY_BIND_PASSWORD, or enable DIRECTORY_INTEGRATED_AUTH=1."
        )
        return None

    try:
        if not conn.bound:
            conn.bind()
    except Exception as exc:  # pragma: no cover - network dependent
        logger.error("Failed to %s bind to directory server: %s", bind_mode, exc)
        try:
            conn.unbind()
        except Exception:
            pass
        return None
    return conn


def _search_directory_raw(query: str, limit: int) -> List[DirectoryUserData]:
    settings = get_auth_settings()
    if not settings.directory_enabled:
        return []

    conn = _create_directory_connection(settings)
    if conn is None:
        return []

    escaped = _escape_ldap_value(_normalise_directory_query(query))
    if not escaped:
        conn.unbind()
        return []

    search_filter = (
        "(|"
        f"(displayName=*{escaped}*)"
        f"(sAMAccountName=*{escaped}*)"
        f"(userPrincipalName=*{escaped}*)"
        f"(mail=*{escaped}*)"
        f"(cn=*{escaped}*)"
        ")"
    )
    attributes = ["sAMAccountName", "displayName", "mail", "userPrincipalName"]

    try:
        conn.search(
            search_base=settings.directory_base_dn,
            search_filter=search_filter,
            attributes=attributes,
            size_limit=limit,
        )
        entries = getattr(conn, "entries", [])
    except Exception as exc:  # pragma: no cover - network dependent
        logger.error("Directory search failed: %s", exc)
        entries = []
    finally:
        try:
            conn.unbind()
        except Exception:
            pass

    results: List[DirectoryUserData] = []
    for entry in entries:
        try:
            sam = str(entry.sAMAccountName) if "sAMAccountName" in entry else None
            username = sam or str(entry.userPrincipalName) if "userPrincipalName" in entry else None
            display_name = str(entry.displayName) if "displayName" in entry else None
            email = str(entry.mail) if "mail" in entry else None
        except Exception:  # pragma: no cover - defensive
            continue
        if not username:
            continue
        results.append(
            DirectoryUserData(
                username=username,
                display_name=display_name,
                email=email,
            )
        )
    return results


@lru_cache(maxsize=256)
def _lookup_directory_user(username: str) -> Optional[DirectoryUserData]:
    if not username:
        return None
    short_username = username.split("\\")[-1]
    results = _search_directory_raw(short_username, limit=1)
    return results[0] if results else None


def resolve_display_name(username: str, current: Optional[str] = None) -> str:
    if current:
        return current
    directory_user = _lookup_directory_user(username)
    if directory_user and directory_user.display_name:
        return directory_user.display_name
    settings = get_auth_settings()
    fallback = settings.fallback_display_name if settings.fallback_username == username else None
    derived = fallback or _derive_display_name_from_username(username)
    return derived


class RoleResponse(CamelModel):
    id: int
    name: str

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "RoleResponse":
        return cls(
            id=row.get("RoleId"),
            name=row.get("RoleName"),
        )


class UserResponse(CamelModel):
    id: Optional[int]
    username: str
    display_name: Optional[str] = None
    role_id: Optional[int] = None
    role_name: Optional[str] = None

    @classmethod
    def from_record(cls, record: UserRecord) -> "UserResponse":
        return cls(
            id=record.id,
            username=record.username,
            display_name=record.display_name,
            role_id=record.role_id,
            role_name=record.role_name,
        )


class UserPatchRequest(CamelModel):
    role_id: int = Field(ge=1)


class UserCreateRequest(CamelModel):
    username: str
    display_name: Optional[str] = None
    role_id: int = Field(ge=1)


class DirectoryUserResponse(CamelModel):
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None

    @classmethod
    def from_directory(cls, data: DirectoryUserData) -> "DirectoryUserResponse":
        return cls(
            username=data.username,
            display_name=data.display_name or _derive_display_name_from_username(data.username),
            email=data.email,
        )


_VALID_THEME_COLOR_IDS = {
    "henkel-red",
    "cobalt-blue",
    "deep-ocean",
    "royal-purple",
    "berry-magenta",
    "emerald-green",
    "pine-green",
    "teal-wave",
    "amber-gold",
    "copper-orange",
    "plum-violet",
    "slate-blue",
}


def _normalise_theme_color(value: Optional[str]) -> Optional[str]:
    candidate = (value or "").strip().lower()
    if not candidate:
        return None
    return candidate if candidate in _VALID_THEME_COLOR_IDS else None


class UserPreferenceResponse(CamelModel):
    username: str
    theme_color: Optional[str] = None

    @classmethod
    def from_row(cls, username: str, row: Optional[Dict[str, Any]]) -> "UserPreferenceResponse":
        return cls(
            username=username,
            theme_color=_normalise_theme_color((row or {}).get("ThemeColor")),
        )


class UserPreferenceUpdateRequest(CamelModel):
    theme_color: Optional[str] = Field(None, max_length=64)

    @field_validator("theme_color")
    @classmethod
    def validate_theme_color(cls, value: Optional[str]) -> Optional[str]:
        normalized = _normalise_theme_color(value)
        if value is not None and value.strip() and normalized is None:
            raise ValueError("themeColor must be one of the supported palette ids.")
        return normalized


users_router = APIRouter(tags=["Users"])


def _is_trusted_proxy_client(request: Request, settings: AuthSettings) -> bool:
    client = request.client
    host = (client.host if client else "").strip()
    if not host:
        return False

    trusted_entries = settings.trusted_proxy_ips
    for entry in trusted_entries:
        candidate = entry.strip()
        if not candidate:
            continue
        if host.lower() == candidate.lower():
            return True
        try:
            if ipaddress.ip_address(host) in ipaddress.ip_network(candidate, strict=False):
                return True
        except ValueError:
            continue
    return False


def _extract_remote_user(request: Request, settings: AuthSettings) -> Optional[str]:
    header_candidates = [
        settings.remote_user_header,
        "X-Remote-User",
        "REMOTE_USER",
        "X-IIS-Authenticated-User",
        "X-Authenticated-User",
        "X-Windows-User",
    ]
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Remote user header candidates: %s", header_candidates)
        logger.debug("Request header names: %s", sorted(set(request.headers.keys())))

    trusted_proxy_client = _is_trusted_proxy_client(request, settings)
    if trusted_proxy_client:
        for header in header_candidates:
            if not header:
                continue
            value = request.headers.get(header)
            if value:
                logger.debug("Remote user header resolved from %s: %s", header, value)
                return value
    else:
        presented_headers = [header for header in header_candidates if header and request.headers.get(header)]
        if presented_headers:
            logger.warning(
                "Ignoring remote user headers from untrusted client host %s.",
                request.client.host if request.client else "unknown",
            )

    scope_user = request.scope.get("user")
    if scope_user and hasattr(scope_user, "is_authenticated"):
        try:
            if scope_user.is_authenticated:  # type: ignore[attr-defined]
                # Starlette/fastapi authentication middlewares may set .display_name or .username
                candidate = getattr(scope_user, "username", None) or getattr(scope_user, "display_name", None)
                if candidate:
                    logger.debug("Remote user resolved from request.scope user: %s", candidate)
                    return candidate
        except Exception:
            pass
    logger.debug("Remote user header not found in request.")
    return None


async def get_current_user(request: Request) -> UserRecord:
    cached_user = getattr(request.state, "current_user", None)
    if cached_user:
        return cached_user

    settings = get_auth_settings()
    username = None
    if settings.windows_auth_enabled:
        username = _extract_remote_user(request, settings)

    if not username and settings.fallback_username:
        username = settings.fallback_username

    if not username:
        logger.warning("Authentication failed: missing remote user header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "User is not authenticated."},
        )

    username = _normalise_username(username)
    try:
        user = _fetch_user_by_username(username)
    except Exception:
        # Underlying function already logged; convert to HTTP error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to load user from database."},
        )

    if not user:
        logger.warning("User %s not found in UserRoles table.", username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": "User is not authorised."},
        )
    request.state.current_user = user
    return user


@app.middleware("http")
async def require_authenticated_user(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS":
        return await call_next(request)
    if path == "/openapi.json" or path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/health"):
        return await call_next(request)
    try:
        await get_current_user(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content=_build_http_exception_payload(exc))
    return await call_next(request)


async def require_admin(user: UserRecord = Depends(get_current_user)) -> UserRecord:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": "User does not have permission to perform this action."},
        )
    return user


@users_router.get("/users/me", response_model=UserResponse)
async def get_me(user: UserRecord = Depends(get_current_user)) -> UserResponse:
    return UserResponse.from_record(user)


@users_router.get("/users/me/preferences", response_model=UserPreferenceResponse)
async def get_my_preferences(user: UserRecord = Depends(get_current_user)) -> UserPreferenceResponse:
    try:
        row = _fetch_user_preferences(user.username)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to load user preferences."},
        )
    return UserPreferenceResponse.from_row(user.username, row)


@users_router.put("/users/me/preferences", response_model=UserPreferenceResponse)
async def update_my_preferences(
    payload: UserPreferenceUpdateRequest,
    user: UserRecord = Depends(get_current_user),
) -> UserPreferenceResponse:
    try:
        row = _save_user_preferences(user.username, payload.theme_color)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to save user preferences."},
        )
    return UserPreferenceResponse.from_row(user.username, row)


@users_router.get("/roles", response_model=List[RoleResponse])
async def get_roles(_: UserRecord = Depends(require_admin)) -> List[RoleResponse]:
    try:
        rows = _fetch_roles()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to load roles."},
        )
    return [RoleResponse.from_row(row) for row in rows]


@users_router.get("/users", response_model=List[UserResponse])
async def get_users(_: UserRecord = Depends(require_admin)) -> List[UserResponse]:
    try:
        users = _fetch_all_users()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to load users."},
        )
    return [UserResponse.from_record(user) for user in users]


@users_router.patch("/users/{user_id}", response_model=UserResponse)
async def patch_user(
    user_id: int,
    payload: UserPatchRequest,
    _: UserRecord = Depends(require_admin),
) -> UserResponse:
    updated = _update_user_role(user_id, payload.role_id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"User with id {user_id} not found."},
        )
    return UserResponse.from_record(updated)


@users_router.post("/users", response_model=UserResponse)
async def create_or_update_user(
    payload: UserCreateRequest,
    response: Response,
    _: UserRecord = Depends(require_admin),
) -> UserResponse:
    normalized_username = _normalise_userroles_username(payload.username)
    record, created = _upsert_user(normalized_username, payload.role_id, payload.display_name)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "User operation failed."},
        )
    if created:
        response.status_code = status.HTTP_201_CREATED
    return UserResponse.from_record(record)


@users_router.get("/directory/search", response_model=List[DirectoryUserResponse])
async def directory_search(
    q: Optional[str] = Query(None, min_length=2, max_length=128),
    prefix: Optional[str] = Query(None, alias="Prefix", min_length=2, max_length=128),
    legacy_prefix: Optional[str] = Query(None, alias="prefix", min_length=2, max_length=128),
    _: UserRecord = Depends(require_admin),
) -> List[DirectoryUserResponse]:
    settings = get_auth_settings()
    if not settings.directory_enabled:
        return []
    query_text = (q or prefix or legacy_prefix or "").strip()
    if len(query_text) < 2:
        return []
    results = _search_directory_raw(query_text, limit=settings.directory_search_size)
    return [DirectoryUserResponse.from_directory(item) for item in results]


@users_router.get("/AutoSuggestName")
async def auto_suggest_name(
    Prefix: Optional[str] = Query(None, min_length=2, max_length=128),
    _: UserRecord = Depends(require_admin),
) -> List[Dict[str, str]]:
    settings = get_auth_settings()
    if not settings.directory_enabled:
        return []
    query_text = (Prefix or "").strip()
    if len(query_text) < 2:
        return []
    results = _search_directory_raw(query_text, limit=settings.directory_search_size)
    return [
        {
            "DisplayName": item.display_name or _derive_display_name_from_username(item.username),
            "EMail": item.email or "",
            "Username": item.username,
        }
        for item in results
    ]


app.include_router(users_router)


def _build_http_exception_payload(exc: HTTPException) -> Dict[str, Any]:
    detail = exc.detail
    message: str
    extra: Dict[str, Any] = {}
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("detail") or "An error occurred.")
        extra = {k: v for k, v in detail.items() if k not in {"message", "detail"}}
    elif isinstance(detail, list):
        message = "Request validation failed."
        extra = {"errors": detail}
    elif detail:
        message = str(detail)
    else:
        message = "An error occurred."
    payload: Dict[str, Any] = {"message": message}
    if extra:
        payload.update(extra)
    return payload


def _find_http_exception_in_group(exc: BaseException) -> Optional[HTTPException]:
    exceptions = getattr(exc, "exceptions", None)
    if not exceptions:
        return None
    for inner in exceptions:
        if isinstance(inner, HTTPException):
            return inner
        if isinstance(inner, BaseException):
            nested = _find_http_exception_in_group(inner)
            if nested:
                return nested
    return None


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content=_build_http_exception_payload(exc))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.debug("Validation error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"message": "Validation error.", "errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    http_exc = _find_http_exception_in_group(exc)
    if http_exc:
        return JSONResponse(status_code=http_exc.status_code, content=_build_http_exception_payload(http_exc))
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "Internal server error."},
    )



@lru_cache(maxsize=1)
def _get_user_roles_display_column() -> Optional[str]:
    try:
        conn = get_conn()
    except Exception as exc:
        logger.error("Failed to connect to database for schema introspection: %s", exc)
        return None

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo'
              AND TABLE_NAME = 'UserRoles'
              AND COLUMN_NAME IN ('DisplayName', 'Display_Name')
            """
        )
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as exc:
        logger.warning("Could not determine DisplayName column for UserRoles: %s", exc)
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _user_record_from_row(row: Dict[str, Any]) -> UserRecord:
    display_value = row.get("DisplayName")
    username = row.get("Username") or row.get("username") or ""
    return UserRecord(
        id=row.get("Id"),
        username=username,
        display_name=resolve_display_name(username, display_value),
        role_id=row.get("Role"),
        role_name=row.get("RoleName"),
    )


def _fetch_user_by_username(username: str) -> Optional[UserRecord]:
    raw_username = _normalise_username(username) if username else ""
    if not raw_username:
        return None
    short_username = _normalise_auth_username(raw_username) or raw_username
    display_column = _get_user_roles_display_column()
    display_sql = f", ur.[{display_column}] AS DisplayName" if display_column else ""
    username_short_expr = _username_short_sql("ur.Username")
    query = f"""
        SELECT ur.Id, ur.Username, ur.Role, r.RoleName{display_sql}
        FROM [dbo].[UserRoles] ur
        LEFT JOIN [dbo].[Roles] r ON ur.Role = r.RoleId
        WHERE UPPER(LTRIM(RTRIM(ur.Username))) = UPPER(LTRIM(RTRIM(?)))
           OR UPPER({username_short_expr}) = UPPER(LTRIM(RTRIM(?)))
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(query, raw_username, short_username)
        row = cursor.fetchone()
        if not row:
            return None
        columns = [col[0] for col in cursor.description]
        return _user_record_from_row(dict(zip(columns, row)))
    except Exception as exc:
        logger.error("Failed to fetch user by username %s: %s", username, exc)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _fetch_user_by_id(user_id: int) -> Optional[UserRecord]:
    display_column = _get_user_roles_display_column()
    display_sql = f", ur.[{display_column}] AS DisplayName" if display_column else ""
    query = f"""
        SELECT ur.Id, ur.Username, ur.Role, r.RoleName{display_sql}
        FROM [dbo].[UserRoles] ur
        LEFT JOIN [dbo].[Roles] r ON ur.Role = r.RoleId
        WHERE ur.Id = ?
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(query, user_id)
        row = cursor.fetchone()
        if not row:
            return None
        columns = [col[0] for col in cursor.description]
        return _user_record_from_row(dict(zip(columns, row)))
    except Exception as exc:
        logger.error("Failed to fetch user by id %s: %s", user_id, exc)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _fetch_roles() -> List[Dict[str, Any]]:
    query = """
        SELECT RoleId, RoleName
        FROM [dbo].[Roles]
        ORDER BY RoleId ASC
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    except Exception as exc:
        logger.error("Failed to fetch roles: %s", exc)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _fetch_all_users() -> List[UserRecord]:
    display_column = _get_user_roles_display_column()
    display_sql = f", ur.[{display_column}] AS DisplayName" if display_column else ""
    query = f"""
        SELECT ur.Id, ur.Username, ur.Role, r.RoleName{display_sql}
        FROM [dbo].[UserRoles] ur
        LEFT JOIN [dbo].[Roles] r ON ur.Role = r.RoleId
        ORDER BY ur.Username ASC
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        return [_user_record_from_row(dict(zip(columns, row))) for row in rows]
    except Exception as exc:
        logger.error("Failed to fetch users: %s", exc)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _user_preferences_table_exists(conn) -> bool:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'dbo'
          AND TABLE_NAME = 'UserPreferences'
        """
    )
    return cursor.fetchone() is not None


def _default_user_preferences(username: str) -> Dict[str, Any]:
    return {
        "Username": username,
        "ThemeColor": None,
    }


def _fetch_user_preferences(username: str) -> Dict[str, Any]:
    normalized_username = _normalise_userroles_username(username)
    if not normalized_username:
        return _default_user_preferences("")

    short_username = _normalise_auth_username(normalized_username) or normalized_username
    username_short_expr = _username_short_sql("[Username]")

    try:
        conn = get_conn()
        if not _user_preferences_table_exists(conn):
            return _default_user_preferences(normalized_username)

        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP 1 [Username], [ThemeColor]
            FROM [dbo].[UserPreferences]
            WHERE UPPER(LTRIM(RTRIM([Username]))) = UPPER(LTRIM(RTRIM(?)))
               OR UPPER({username_short_expr}) = UPPER(LTRIM(RTRIM(?)))
            """,
            normalized_username,
            short_username,
        )
        row = cursor.fetchone()
        if not row:
            return _default_user_preferences(normalized_username)
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row))
    except Exception as exc:
        logger.error("Failed to fetch preferences for %s: %s", username, exc)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _save_user_preferences(username: str, theme_color: Optional[str]) -> Dict[str, Any]:
    normalized_username = _normalise_userroles_username(username)
    if not normalized_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "User preference username is missing."},
        )

    normalized_theme = _normalise_theme_color(theme_color)
    if theme_color is not None and theme_color.strip() and normalized_theme is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Theme color is not supported."},
        )

    short_username = _normalise_auth_username(normalized_username) or normalized_username
    username_short_expr = _username_short_sql("[Username]")

    try:
        conn = get_conn()
        if not _user_preferences_table_exists(conn):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"message": "User preferences table is not deployed yet."},
            )

        cursor = conn.cursor()
        cursor.execute(
            f"""
            UPDATE [dbo].[UserPreferences]
            SET [ThemeColor] = ?,
                [UpdatedAt] = SYSUTCDATETIME()
            WHERE UPPER(LTRIM(RTRIM([Username]))) = UPPER(LTRIM(RTRIM(?)))
               OR UPPER({username_short_expr}) = UPPER(LTRIM(RTRIM(?)))
            """,
            normalized_theme,
            normalized_username,
            short_username,
        )
        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO [dbo].[UserPreferences] (
                    [Username],
                    [ThemeColor]
                )
                VALUES (?, ?)
                """,
                normalized_username,
                normalized_theme,
            )
        conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to save preferences for %s: %s", username, exc)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return _fetch_user_preferences(normalized_username)


def _update_user_role(user_id: int, role_id: int) -> Optional[UserRecord]:
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE [dbo].[UserRoles]
            SET Role = ?
            WHERE Id = ?
            """,
            role_id,
            user_id,
        )
        if cursor.rowcount == 0:
            conn.rollback()
            return None
        conn.commit()
    except Exception as exc:
        logger.error("Failed to update user %s role: %s", user_id, exc)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return _fetch_user_by_id(user_id)


def _insert_user(username: str, role_id: int, display_name: Optional[str]) -> UserRecord:
    display_column = _get_user_roles_display_column()
    columns = ["Username", "Role"]
    params: List[Any] = [username, role_id]
    placeholders = ["?", "?"]
    if display_column:
        columns.append(display_column)
        params.append(display_name or _derive_display_name_from_username(username))
        placeholders.append("?")

    column_sql = ", ".join(f"[{col}]" for col in columns)
    placeholders_sql = ", ".join(placeholders)

    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            INSERT INTO [dbo].[UserRoles] ({column_sql})
            VALUES ({placeholders_sql})
            """,
            params,
        )
        conn.commit()
    except Exception as exc:
        logger.error("Failed to insert user %s: %s", username, exc)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

    created = _fetch_user_by_username(username)
    if not created:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"User {username} could not be loaded after insert."},
        )
    return created


def _upsert_user(username: str, role_id: int, display_name: Optional[str]) -> Tuple[UserRecord, bool]:
    existing = _fetch_user_by_username(username)
    if existing:
        try:
            conn = get_conn()
            cursor = conn.cursor()
            display_column = _get_user_roles_display_column()
            if display_column:
                cursor.execute(
                    f"""
                    UPDATE [dbo].[UserRoles]
                    SET Role = ?, [{display_column}] = ?
                    WHERE Id = ?
                    """,
                    role_id,
                    display_name or _derive_display_name_from_username(username),
                    existing.id,
                )
            else:
                cursor.execute(
                    """
                    UPDATE [dbo].[UserRoles]
                    SET Role = ?
                    WHERE Id = ?
                    """,
                    role_id,
                    existing.id,
                )
            conn.commit()
        except Exception as exc:
            logger.error("Failed to update user %s: %s", username, exc)
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass
        refreshed = _fetch_user_by_id(existing.id) if existing.id else _fetch_user_by_username(username)
        return (refreshed or existing, False)
    else:
        created = _insert_user(username, role_id, display_name)
        return (created, True)


def _clean_text(value, upper: bool = False):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.upper() if upper else text


def _clean_date(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_flag(value) -> int:
    if value in (1, "1", True, "true", "True"):
        return 1
    return 0


def _prepare_payload_dict(payload):
    return {
        "Country": _clean_text(getattr(payload, "Country", None), upper=True),
        "Status": _clean_text(getattr(payload, "Status", None)),
        "Name_Surname": _clean_text(getattr(payload, "Name_Surname", None)),
        "Identity": _clean_text(getattr(payload, "Identity", None)),
        "Department": _clean_text(getattr(payload, "Department", None)),
        "Region": _clean_text(getattr(payload, "Region", None)),
        "Hardware_Type": _clean_text(getattr(payload, "Hardware_Type", None)),
        "Hardware_Manufacturer": _clean_text(getattr(payload, "Hardware_Manufacturer", None)),
        "Hardware_Model": _clean_text(getattr(payload, "Hardware_Model", None)),
        "Hardware_Serial_Number": _clean_text(getattr(payload, "Hardware_Serial_Number", None)),
        "Asset_Number": _clean_text(getattr(payload, "Asset_Number", None)),
        "Capitalization_Date": _clean_date(getattr(payload, "Capitalization_Date", None)),
        "User_Name": _clean_text(getattr(payload, "User_Name", None)),
        "Old_User": _clean_text(getattr(payload, "Old_User", None)),
        "Windows_Computer_Name": _clean_text(getattr(payload, "Windows_Computer_Name", None)),
        "Win_OS": _clean_text(getattr(payload, "Win_OS", None)),
        "Location_Floor": _clean_text(getattr(payload, "Location_Floor", None)),
        "Notes": _clean_text(getattr(payload, "Notes", None)),
        "If_Deleted": _normalize_flag(getattr(payload, "If_Deleted", 0)),
    }


def _prepare_payload_params(payload):
    data = _prepare_payload_dict(payload)
    for field in REQUIRED_DB_STR_FIELDS:
        if data.get(field) is None:
            data[field] = ""
    return data, [
        data["Country"],
        data["Status"],
        data["Name_Surname"],
        data["Identity"],
        data["Department"],
        data["Region"],
        data["Hardware_Type"],
        data["Hardware_Manufacturer"],
        data["Hardware_Model"],
        data["Hardware_Serial_Number"],
        data["Asset_Number"],
        data["Capitalization_Date"],
        data["User_Name"],
        data["Old_User"],
        data["Windows_Computer_Name"],
        data["Win_OS"],
        data["Location_Floor"],
        data["Notes"],
        data["If_Deleted"],
    ]


WRITE_COLUMN_SQL = {
    "Country": "[Country]",
    "Status": "[Status]",
    "Name_Surname": "[Name_Surname]",
    "Identity": "[Identity]",
    "Department": "[Department]",
    "Region": "[Region]",
    "Hardware_Type": "[Hardware_Type]",
    "Hardware_Manufacturer": "[Hardware_Manufacturer]",
    "Hardware_Model": "[Hardware_Model]",
    "Hardware_Serial_Number": "[Hardware_Serial_Number]",
    "Asset_Number": "[Asset_Number]",
    "Capitalization_Date": "[Capitalization_Date]",
    "User_Name": "[User_Name]",
    "Old_User": "[Old_User]",
    "Windows_Computer_Name": "[Windows_Computer_Name]",
    "Win_OS": "[Win_OS]",
    "Location_Floor": "[Location/Floor]",
    "Notes": "[Notes]",
    "If_Deleted": "[If_Deleted]",
}


REQUIRED_DB_STR_FIELDS = {
    "Identity",
    "Region",
    "Hardware_Type",
    "Hardware_Manufacturer",
    "Windows_Computer_Name",
    "Win_OS",
    "User_Name",
}


def _build_exact_match_sql(cleaned):
    clauses = []
    params: List[object] = []
    for key, column_sql in WRITE_COLUMN_SQL.items():
        value = cleaned.get(key)
        if value is None:
            clauses.append(f"{column_sql} IS NULL")
        else:
            clauses.append(f"{column_sql} = ?")
            params.append(value)
    where = " AND ".join(clauses) if clauses else "1=1"
    return where, params


UPDATE_ITEM_SQL = """
UPDATE [dbo].[ITHardware]
SET
  Country = ?,
  Status = ?,
  Name_Surname = ?,
  [Identity] = ?,
  Department = ?,
  Region = ?,
  Hardware_Type = ?,
  Hardware_Manufacturer = ?,
  Hardware_Model = ?,
  Hardware_Serial_Number = ?,
  Asset_Number = ?,
  Capitalization_Date = TRY_CONVERT(date, ?, 23),
  User_Name = ?,
  Old_User = ?,
  Windows_Computer_Name = ?,
  Win_OS = ?,
  [Location/Floor] = ?,
  Notes = ?,
  If_Deleted = ?
WHERE {where_clause};
"""


PARAM_FILTERS = {
    "country": ("[Country]", "like"),
    "status": ("[Status]", "like"),
    "name_surname": ("[Name_Surname]", "like"),
    "identity": ("[Identity]", "like"),
    # Department yalnızca kod kısmına göre filtrelensin
    "department": ("[Department]", "dept_code_like"),
    "region": ("[Region]", "like"),
    "hardware_type": ("[Hardware_Type]", "like"),
    "hardware_manufacturer": ("[Hardware_Manufacturer]", "like"),
    "hardware_model": ("[Hardware_Model]", "like"),
    "win_os": ("[Win_OS]", "like"),
    "user_name": ("[User_Name]", "like"),
    "old_user": ("[Old_User]", "like"),
    "windows_computer_name": ("[Windows_Computer_Name]", "like"),
    "location_floor": ("[Location/Floor]", "like"),
    "notes": ("[Notes]", "like"),
    "hardware_serial_number": ("[Hardware_Serial_Number]", "like"),
    "asset_number": ("[Asset_Number]", "like"),
    "if_deleted": ("[If_Deleted]", "exact"),
}

COUNTRY_ALIASES = {
    "tr": "TR",
    "turkey": "TR",
    "turkiye": "TR",
    "sa": "SA",
    "ksa": "SA",
    "saudi arabia": "SA",
    "the kingdom of saudi arabia": "SA",
    "kingdom of saudi arabia": "SA",
    "suudi arabistan": "SA",
    "jo": "JO",
    "jordan": "JO",
    "jordania": "JO",
    "jordanya": "JO",
    "hashemite kingdom of jordan": "JO",
    "il": "IL",
    "israel": "IL",
    "state of israel": "IL",
    "israil": "IL",
    "ae": "AE",
    "uae": "AE",
    "u.a.e": "AE",
    "united arab emirates": "AE",
    "birlesik arap emirlikleri": "AE",
}

SEARCHABLE_COLUMNS = {
    "Country": ("[Country]", "like"),
    "Status": ("[Status]", "like"),
    "Name_Surname": ("[Name_Surname]", "like"),
    "Identity": ("[Identity]", "like"),
    # Global column search'ta da Department kodu baz alınsın
    "Department": ("[Department]", "dept_code_like"),
    "Region": ("[Region]", "like"),
    "Hardware_Type": ("[Hardware_Type]", "like"),
    "Hardware_Manufacturer": ("[Hardware_Manufacturer]", "like"),
    "Hardware_Model": ("[Hardware_Model]", "like"),
    "Hardware_Serial_Number": ("[Hardware_Serial_Number]", "like"),
    "Asset_Number": ("[Asset_Number]", "like"),
    "Capitalization_Date": ("[Capitalization_Date]", "date_like"),
    "User_Name": ("[User_Name]", "like"),
    "Old_User": ("[Old_User]", "like"),
    "Windows_Computer_Name": ("[Windows_Computer_Name]", "like"),
    "Win_OS": ("[Win_OS]", "like"),
    "Location_Floor": ("[Location/Floor]", "like"),
    "Notes": ("[Notes]", "like"),
    "If_Deleted": ("[If_Deleted]", "exact"),
    "Age": ("[Age]", "number"),
}

SEARCHABLE_COLUMN_LOOKUP = {
    key.lower(): value for key, value in SEARCHABLE_COLUMNS.items()
}
SEARCHABLE_COLUMN_LOOKUP.update(
    {
        key.replace("_", " ").lower(): value
        for key, value in SEARCHABLE_COLUMNS.items()
    }
)

CHOICE_FIELDS = [
    "Country",
    "Department",
    "Hardware_Manufacturer",
    "Hardware_Model",
    "Hardware_Type",
    "Identity",
    "Location_Floor",
    "Region",
    "Status",
    "Win_OS",
]

CHOICE_FIELD_LOOKUP = {field.lower(): field for field in CHOICE_FIELDS}
FIELD_PARAM_COLUMN_SQL = {
    "Country": "[Country]",
    "Department": "[Department]",
    "Hardware_Manufacturer": "[Hardware_Manufacturer]",
    "Hardware_Model": "[Hardware_Model]",
    "Hardware_Type": "[Hardware_Type]",
    "Identity": "[Identity]",
    "Location_Floor": "[Location/Floor]",
    "Region": "[Region]",
    "Status": "[Status]",
    "Win_OS": "[Win_OS]",
}


class FieldParamItem(BaseModel):
    value: str
    usage_count: int
    managed: bool = True


class FieldParametersResponse(BaseModel):
    fields: Dict[str, List[FieldParamItem]]


class FieldParamCreate(BaseModel):
    value: str = Field(..., min_length=1, max_length=255)

    @field_validator("value")
    def normalise_value(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("Value cannot be empty.")
        return value


class FieldParamUpdate(BaseModel):
    original: str = Field(..., min_length=1, max_length=255)
    value: str = Field(..., min_length=1, max_length=255)
    update_existing: bool = True

    @field_validator("original", "value")
    def normalise_update_values(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("Value cannot be empty.")
        return value


def _ensure_choice_field(field: str) -> str:
    if not field:
        raise HTTPException(status_code=404, detail="Field name is required.")
    key = field.strip().lower()
    canonical = CHOICE_FIELD_LOOKUP.get(key)
    if not canonical:
        raise HTTPException(status_code=404, detail=f"Unsupported field '{field}'.")
    return canonical


def _normalise_param_value(value: str) -> str:
    trimmed = (value or "").strip()
    if not trimmed:
        raise HTTPException(status_code=400, detail="Value cannot be empty.")
    return trimmed


def _field_column_sql(field: str) -> str:
    try:
        return FIELD_PARAM_COLUMN_SQL[field]
    except KeyError as exc:
        raise HTTPException(status_code=500, detail=f"Missing column mapping for field '{field}'.") from exc


def _get_usage_count(conn, field: str, value: str) -> int:
    column_sql = _field_column_sql(field)
    trim_expr = f"LTRIM(RTRIM({column_sql}))"
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM [dbo].[ITHardware] WHERE {trim_expr} = ?", value)
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _fetch_field_params(conn, field: str) -> List[Dict[str, object]]:
    canonical = _ensure_choice_field(field)
    column_sql = _field_column_sql(canonical)
    managed_values: List[str] = []
    cur = conn.cursor()
    cur.execute("SELECT ParamName FROM FieldParams WHERE FieldName = ? ORDER BY ParamName ASC", canonical)
    for (raw_value,) in cur.fetchall():
        value = (raw_value or "").strip()
        if value and value not in managed_values:
            managed_values.append(value)
    trim_expr = f"LTRIM(RTRIM({column_sql}))"
    usage_counts: Dict[str, int] = {}
    cur.execute(f"SELECT {trim_expr} AS ParamValue, COUNT(*) FROM [dbo].[ITHardware] GROUP BY {trim_expr}")
    for raw_value, count in cur.fetchall():
        value = (raw_value or "").strip()
        if not value:
            continue
        usage_counts[value] = int(count)
    items: List[Dict[str, object]] = []
    seen = set()
    for value in managed_values:
        usage = usage_counts.get(value, 0)
        items.append({"value": value, "usage_count": usage, "managed": True})
        seen.add(value)
    for value, usage in usage_counts.items():
        if value not in seen:
            items.append({"value": value, "usage_count": usage, "managed": False})
    items.sort(key=lambda item: (0 if item.get("managed") else 1, item["value"].lower()))
    return items


TEXT_SEARCH_COLLATION = "Turkish_100_CI_AI"
NULL_FILTER_TOKEN = "__NULL_FILTER__"


def _split_text_search_terms(value: object) -> List[str]:
    if value is None:
        return []
    return [segment for segment in str(value).strip().split() if segment]


def _is_null_filter_value(value: object) -> bool:
    return isinstance(value, str) and value.strip() == NULL_FILTER_TOKEN


def _append_null_filter(clauses, column_sql):
    blank_expr = f"NULLIF(LTRIM(RTRIM(CAST({column_sql} AS nvarchar(max)))), '')"
    clauses.append(f"{blank_expr} IS NULL")


def _append_filter(clauses, params, column_sql, operator, raw_value):
    if raw_value is None:
        return

    if isinstance(raw_value, str):
        value = raw_value.strip()
    else:
        value = raw_value

    if value is None or value == "":
        return

    if _is_null_filter_value(value):
        _append_null_filter(clauses, column_sql)
        return

    if operator == "exact":
        clauses.append(f"{column_sql} = ?")
        params.append(value)

    elif operator == "like":
        search_terms = _split_text_search_terms(value)
        if not search_terms:
            return
        text_expr = f"LTRIM(RTRIM(CAST({column_sql} AS nvarchar(max)))) COLLATE {TEXT_SEARCH_COLLATION}"
        # Trim + upper ile sağlamlaştır
        clauses.append("(" + " AND ".join([f"{text_expr} LIKE ?" for _ in search_terms]) + ")")
        params.extend([f"%{term}%" for term in search_terms])

    elif operator == "dept_code_like":
    # "Business Unit - Example Division" -> "BU"
        code_expr = f"""
            UPPER(LTRIM(RTRIM(
                CASE
                    WHEN CHARINDEX('-', {column_sql}) > 0
                        THEN LEFT({column_sql}, CHARINDEX('-', {column_sql}) - 1)
                    ELSE {column_sql}
                END
            )))
        """
        text_value = str(value).strip().upper()
        if not text_value:
            return
        clauses.append(f"{code_expr} LIKE ?")
        params.append(f"%{text_value}%")

    elif operator == "number":
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid numeric search value.")
        clauses.append(f"{column_sql} = ?")
        params.append(numeric_value)

    elif operator == "date_gte":
        clauses.append(f"{column_sql} >= TRY_CONVERT(date, ?, 23)")
        params.append(value)

    elif operator == "date_lte":
        clauses.append(f"{column_sql} <= TRY_CONVERT(date, ?, 23)")
        params.append(value)

    elif operator == "date_like":
        clauses.append(f"CONVERT(varchar(10), {column_sql}, 23) LIKE ?")
        params.append(f"%{value}%")

    else:
        raise HTTPException(status_code=400, detail="Unsupported filter operator.")

def _normalise_country_code(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if _is_null_filter_value(value):
        return NULL_FILTER_TOKEN
    if isinstance(value, str):
        key = value.strip().lower()
        if not key:
            return None
        return COUNTRY_ALIASES.get(key, value.strip().upper())
    return str(value).strip().upper()

# -----------------------------
# server ve db ayakta mı?
# -----------------------------
@app.get("/health")
def health():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT @@SERVERNAME, DB_NAME()")
        server, db = cur.fetchone()
    return {"ok": True, "server": server, "db": db}

@app.get("/count")
def count_all():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM [dbo].[ITHardware]")
        total = cur.fetchone()[0]
    return {"total": total}

@app.get("/field-parameters", response_model=FieldParametersResponse)
def list_field_parameters():
    with get_conn() as conn:
        fields = {field: _fetch_field_params(conn, field) for field in CHOICE_FIELDS}
    return {"fields": fields}


@app.get("/field-parameters/{field}", response_model=List[FieldParamItem])
def get_field_parameters(field: str):
    canonical = _ensure_choice_field(field)
    with get_conn() as conn:
        return _fetch_field_params(conn, canonical)


@app.post("/field-parameters/{field}", response_model=FieldParamItem, status_code=201)
def create_field_parameter(field: str, payload: FieldParamCreate):
    canonical = _ensure_choice_field(field)
    value = payload.value
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM FieldParams WHERE FieldName = ? AND UPPER(LTRIM(RTRIM(ParamName))) = UPPER(?)",
            canonical,
            value,
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="This value already exists for the selected field.")
        cur.execute("INSERT INTO FieldParams (FieldName, ParamName) VALUES (?, ?)", canonical, value)
        conn.commit()
        usage_count = _get_usage_count(conn, canonical, value)
    return {"value": value, "usage_count": usage_count, "managed": True}


@app.put("/field-parameters/{field}", response_model=FieldParamItem)
def update_field_parameter(field: str, payload: FieldParamUpdate):
    canonical = _ensure_choice_field(field)
    original = payload.original
    new_value = payload.value
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT ParamName FROM FieldParams WHERE FieldName = ? AND RTRIM(LTRIM(ParamName)) = ?",
            canonical,
            original,
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="The specified value was not found.")
        stored_original = row[0]
        if new_value.lower() != original.lower():
            cur.execute(
                "SELECT 1 FROM FieldParams WHERE FieldName = ? AND UPPER(LTRIM(RTRIM(ParamName))) = UPPER(?)",
                canonical,
                new_value,
            )
            existing = cur.fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="Another parameter already uses this value.")
        cur.execute(
            "UPDATE FieldParams SET ParamName = ? WHERE FieldName = ? AND ParamName = ?",
            new_value,
            canonical,
            stored_original,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Value update failed.")
        if payload.update_existing and new_value.lower() != original.lower():
            column_sql = _field_column_sql(canonical)
            trim_expr = f"LTRIM(RTRIM({column_sql}))"
            cur.execute(
                f"UPDATE [dbo].[ITHardware] SET {column_sql} = ? WHERE {trim_expr} = ?",
                new_value,
                stored_original.strip(),
            )
        conn.commit()
        usage_count = _get_usage_count(conn, canonical, new_value)
    return {"value": new_value, "usage_count": usage_count, "managed": True}


@app.delete("/field-parameters/{field}/{value}")
def delete_field_parameter(
    field: str,
    value: str,
    force: bool = Query(False),
    replacement: Optional[str] = Query(None),
):
    canonical = _ensure_choice_field(field)
    target_value = _normalise_param_value(value)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT ParamName FROM FieldParams WHERE FieldName = ? AND RTRIM(LTRIM(ParamName)) = ?",
            canonical,
            target_value,
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Value not found.")
        stored_value = row[0]
        usage_count = _get_usage_count(conn, canonical, stored_value.strip())
        applied_replacement: Optional[str] = None
        column_sql = _field_column_sql(canonical)
        trim_expr = f"LTRIM(RTRIM({column_sql}))"
        affected = 0
        if usage_count > 0:
            if replacement:
                replacement_value = _normalise_param_value(replacement)
                cur.execute(
                    "SELECT ParamName FROM FieldParams WHERE FieldName = ? AND RTRIM(LTRIM(ParamName)) = ?",
                    canonical,
                    replacement_value,
                )
                rep_row = cur.fetchone()
                if not rep_row:
                    raise HTTPException(status_code=404, detail="Replacement value is not registered.")
                applied_replacement = rep_row[0].strip()
                if applied_replacement.lower() == stored_value.strip().lower():
                    raise HTTPException(status_code=400, detail="Replacement must be different from the removed value.")
                cur.execute(
                    f"UPDATE [dbo].[ITHardware] SET {column_sql} = ? WHERE {trim_expr} = ?",
                    applied_replacement,
                    stored_value.strip(),
                )
                affected = cur.rowcount
            elif force:
                cur.execute(
                    f"UPDATE [dbo].[ITHardware] SET {column_sql} = NULL WHERE {trim_expr} = ?",
                    stored_value.strip(),
                )
                affected = cur.rowcount
            else:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": f"Cannot delete '{stored_value.strip()}' while it is used in {usage_count} records.",
                        "usage_count": usage_count,
                        "requires_replacement": True,
                    },
                )
        cur.execute(
            "DELETE FROM FieldParams WHERE FieldName = ? AND ParamName = ?",
            canonical,
            stored_value,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Deletion failed.")
        conn.commit()
    return {
        "value": stored_value.strip(),
        "removed": True,
        "affected_records": affected,
        "replacement": applied_replacement,
        "usage_before": usage_count,
    }


# -----------------------------
# Yeni kayıt oluşturma (POST)
# -----------------------------
class HardwareCreate(BaseModel):
    Name_Surname: str = Field(..., min_length=1, max_length=50)
    Hardware_Serial_Number: str = Field(..., min_length=1, max_length=50)
    Asset_Number: str = Field(..., min_length=1, max_length=50)

    Country: str = Field(..., min_length=2, max_length=2)
    Identity: Optional[str] = Field(None, max_length=10)
    Region: Optional[str] = Field(None, max_length=8)
    Win_OS: Optional[str] = Field(None, max_length=15)
    Hardware_Type: Optional[str] = Field(None, max_length=20)
    Hardware_Manufacturer: Optional[str] = Field(None, max_length=60)
    Windows_Computer_Name: Optional[str] = Field(None, max_length=100)
    User_Name: Optional[str] = Field(None, max_length=30)

    Status: Optional[str] = Field(None, max_length=30)
    Department: Optional[str] = Field(None, max_length=50)
    Hardware_Model: Optional[str] = Field(None, max_length=60)
    Location_Floor: Optional[str] = Field(None, max_length=100)
    Capitalization_Date: Optional[Union[str, date]] = Field(None, description="YYYY-MM-DD")
    Old_User: Optional[str] = None
    Notes: Optional[str] = None
    If_Deleted: Optional[int] = Field(0, ge=0, le=1)

    # INSERT edilemeyen/computed gibi davranan alan
    Age: Optional[float] = Field(None, ge=0)

    @field_validator("Asset_Number", mode="before")
    def coerce_asset_to_str(cls, v):
        return str(v) if v is not None else v

    @field_validator("Capitalization_Date", mode="before")
    def coerce_date_to_iso(cls, v):
        try:
            if isinstance(v, date):
                return v.isoformat()
        except Exception:
            pass
        return v

@app.post("/items", status_code=201)
def create_item(payload: HardwareCreate):
    sql = """
    INSERT INTO [dbo].[ITHardware] (
        Country, Status, Name_Surname, [Identity], Department, Region,
        Hardware_Type, Hardware_Manufacturer, Hardware_Model,
        Hardware_Serial_Number, Asset_Number,
        Capitalization_Date, User_Name, Old_User,
        Windows_Computer_Name, Win_OS, [Location/Floor], Notes,
        If_Deleted
    )
    VALUES (
        ?, ?, ?, ?, ?, ?,
        ?, ?, ?,
        ?, ?,
        TRY_CONVERT(date, ?, 23), ?, ?,
        ?, ?, ?, ?,
        ?
    );
    """

    cleaned, params = _prepare_payload_params(payload)

    with get_conn() as conn:
        cur = conn.cursor()
        try:
            # Duplicate serial check
            serial = cleaned.get("Hardware_Serial_Number")
            if serial:
                cur.execute(
                    "SELECT TOP 1 ID FROM [dbo].[ITHardware] WHERE [Hardware_Serial_Number] = ?",
                    serial,
                )
                if cur.fetchone():
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "duplicate_serial",
                            "message": "An item with this hardware serial number already exists.",
                        },
                    )

            # Exact row duplicate check
            where_sql, match_params = _build_exact_match_sql(cleaned)
            cur.execute(
                f"SELECT TOP 1 ID FROM [dbo].[ITHardware] WHERE {where_sql}",
                match_params,
            )
            if cur.fetchone():
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "duplicate_row",
                        "message": "An identical item is already registered in the inventory.",
                    },
                )

            cur.execute(sql, params)
            conn.commit()
        except HTTPException as http_err:
            conn.rollback()
            raise http_err
        except Exception as e:
            conn.rollback()
            logger.exception("Failed to create inventory item.")
            raise HTTPException(status_code=500, detail={"message": "Failed to create item."}) from e
        new_id = None
        try:
            cur.execute("SELECT SCOPE_IDENTITY()")
            row = cur.fetchone()
            if row:
                new_id = row[0]
        except Exception:
            new_id = None
    return {"ok": True, "id": new_id}


@app.put("/items/{item_ref}")
def update_item(item_ref: str, payload: HardwareCreate):
    cleaned, params = _prepare_payload_params(payload)
    reference = _clean_text(item_ref)
    if not reference:
        raise HTTPException(status_code=400, detail="Invalid item reference.")
    with get_conn() as conn:
        cur = conn.cursor()
        target_id: Optional[int] = None
        updated = 0
        try:
            try:
                candidate_id = int(reference)
            except (TypeError, ValueError):
                candidate_id = None

            # First, try to resolve by DB ID if the reference looks numeric
            if candidate_id is not None:
                cur.execute("SELECT ID FROM [dbo].[ITHardware] WHERE [ID] = ?", candidate_id)
                row = cur.fetchone()
                if row:
                    target_id = row[0]

            # Fallback: resolve by Asset_Number (covers numeric asset numbers, too)
            if target_id is None:
                cur.execute("SELECT ID FROM [dbo].[ITHardware] WHERE [Asset_Number] = ?", reference)
                row = cur.fetchone()
                if row:
                    target_id = row[0]

            if target_id is None:
                conn.rollback()
                raise HTTPException(status_code=404, detail="Item not found.")

            # Duplicate serial check excluding the row being updated
            serial = cleaned.get("Hardware_Serial_Number")
            if serial:
                cur.execute(
                    "SELECT ID FROM [dbo].[ITHardware] WHERE [Hardware_Serial_Number] = ? AND [ID] <> ?",
                    serial,
                    target_id,
                )
                if cur.fetchone():
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "duplicate_serial",
                            "message": "An item with this hardware serial number already exists.",
                        },
                    )

            cur.execute(
                UPDATE_ITEM_SQL.format(where_clause="[ID] = ?"),
                [*params, target_id],
            )
            updated = cur.rowcount
            if updated == 0:
                conn.rollback()
                raise HTTPException(status_code=404, detail="Item not found.")
            conn.commit()
        except HTTPException as http_err:
            conn.rollback()
            raise http_err
        except Exception as exc:
            conn.rollback()
            logger.exception("Failed to update inventory item %s.", item_ref)
            raise HTTPException(status_code=500, detail={"message": "Failed to update item."}) from exc
    resolved = target_id if (target_id is not None and updated) else reference
    return {"ok": True, "updated": updated, "id": resolved}


@app.delete("/items/{item_ref}")
def delete_item(item_ref: str):
    reference = _clean_text(item_ref)
    if not reference:
        raise HTTPException(status_code=400, detail="Invalid item reference.")
    with get_conn() as conn:
        cur = conn.cursor()
        deleted = 0
        candidate_id: Optional[int] = None
        try:
            candidate_id = int(reference)
        except (TypeError, ValueError):
            candidate_id = None
        try:
            if candidate_id is not None:
                cur.execute("DELETE FROM [dbo].[ITHardware] WHERE [ID] = ?", candidate_id)
                deleted = cur.rowcount
            if deleted == 0:
                cur.execute("DELETE FROM [dbo].[ITHardware] WHERE [Asset_Number] = ?", reference)
                deleted = cur.rowcount
            if deleted == 0:
                conn.rollback()
                raise HTTPException(status_code=404, detail="Item not found.")
            conn.commit()
        except HTTPException:
            raise
        except Exception as exc:
            conn.rollback()
            logger.exception("Failed to delete inventory item %s.", item_ref)
            raise HTTPException(status_code=500, detail={"message": "Failed to delete item."}) from exc
    return {"ok": True, "deleted": deleted}

# -------------------------------------------
# Ülke bazında spare oranları
# -------------------------------------------
@app.get("/spare_ratios")
def spare_ratios():
    sql = """
    SELECT
        Country,
        COUNT(*) AS total,
        SUM(CASE WHEN Status = 'In Inventory' THEN 1 ELSE 0 END) AS spare
    FROM [dbo].[ITHardware]
    GROUP BY Country
    ORDER BY Country;
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        rows = []
        for country, total, spare in cur.fetchall():
            total = total or 0
            spare = spare or 0
            ratio = (spare / total) if total > 0 else 0
            rows.append({
                "country": country,
                "total": total,
                "spare": spare,
                "ratio": ratio,
                "ratio_pct": round(ratio * 100, 2)
            })
    return {"items": rows, "count": len(rows)}

# -------------------------------------------
# Filtreli listeleme (paging + toplam)
# -------------------------------------------
@app.get("/rows")
def rows(
    country: Optional[str] = None,
    status: Optional[str] = None,
    name_surname: Optional[str] = None,
    identity: Optional[str] = None,
    department: Optional[str] = None,
    region: Optional[str] = None,
    hardware_type: Optional[str] = None,
    hardware_manufacturer: Optional[str] = None,
    hardware_model: Optional[str] = None,
    win_os: Optional[str] = None,
    user_name: Optional[str] = None,
    old_user: Optional[str] = None,
    windows_computer_name: Optional[str] = None,
    location_floor: Optional[str] = None,
    notes: Optional[str] = None,
    hardware_serial_number: Optional[str] = None,
    asset_number: Optional[str] = None,
    if_deleted: Optional[int] = Query(0, ge=0, le=1),
    age_min: float = Query(0, ge=0),
    age_max: float = Query(1000, ge=0),
    capitalization_date_from: Optional[str] = Query(None, alias="capitalization_date_from"),
    capitalization_date_to: Optional[str] = Query(None, alias="capitalization_date_to"),
    limit: int = Query(100, ge=1, le=1000000),
    offset: int = Query(0, ge=0),
    column: Optional[str] = None,
    search: Optional[str] = None,
):
    if age_min > age_max:
        raise HTTPException(status_code=400, detail="age_min cannot be greater than age_max.")

    normalised_country = _normalise_country_code(country)

    filter_values = {
        "country": normalised_country,
        "status": status,
        "name_surname": name_surname,
        "identity": identity,
        "department": department,
        "region": region,
        "hardware_type": hardware_type,
        "hardware_manufacturer": hardware_manufacturer,
        "hardware_model": hardware_model,
        "win_os": win_os,
        "user_name": user_name,
        "old_user": old_user,
        "windows_computer_name": windows_computer_name,
        "location_floor": location_floor,
        "notes": notes,
        "hardware_serial_number": hardware_serial_number,
        "asset_number": asset_number,
        "if_deleted": if_deleted,
    }

    where_clauses = ["([Age] IS NULL OR TRY_CONVERT(float, NULLIF(LTRIM(RTRIM(CAST([Age] AS nvarchar(64)))), '')) BETWEEN ? AND ?)"]
    params = [age_min, age_max]

    def add_filter(column_sql: str, operator: str, raw_value):
        _append_filter(where_clauses, params, column_sql, operator, raw_value)

    add_filter("[Capitalization_Date]", "date_gte", capitalization_date_from)
    add_filter("[Capitalization_Date]", "date_lte", capitalization_date_to)

    for key, (column_sql, operator) in PARAM_FILTERS.items():
        add_filter(column_sql, operator, filter_values.get(key))

    search_key = (column or "").strip().lower()
    search_value = (search or "").strip()
    if search_value and search_key:
        lookup_key = search_key
        search_column_info = SEARCHABLE_COLUMN_LOOKUP.get(lookup_key)
        if not search_column_info:
            search_column_info = SEARCHABLE_COLUMN_LOOKUP.get(lookup_key.replace("_", " "))
        if search_column_info:
            column_sql, operator = search_column_info
            _append_filter(where_clauses, params, column_sql, operator, search_value)

    where_sql = " AND ".join(["1=1", *where_clauses])

    select_sql = f"""
        SELECT
          ID,
          Country,
          Status,
          Name_Surname,
          [Identity],
          Department,
          Region,
          Hardware_Type,
          Hardware_Manufacturer,
          Hardware_Model,
          Hardware_Serial_Number,
          Asset_Number,
          Capitalization_Date,
          Age,
          User_Name,
          Old_User,
          Windows_Computer_Name,
          Win_OS,
          [Location/Floor] AS Location_Floor,
          Notes,
          [If_Deleted] AS If_Deleted
        FROM [dbo].[ITHardware]
        WHERE {where_sql}
        ORDER BY
          Capitalization_Date DESC,
          Country ASC,
          Name_Surname ASC
        OFFSET CAST(? AS INT) ROWS FETCH NEXT CAST(? AS INT) ROWS ONLY;
        """

    count_sql = f"""
    SELECT COUNT(*)
    FROM [dbo].[ITHardware]
    WHERE {where_sql};
    """

    base_params = list(params)
    count_params = base_params.copy()
    page_params = base_params + [int(offset), int(limit)]

    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(count_sql, count_params)
            total_count = cur.fetchone()[0]

            cur.execute(select_sql, page_params)
            cols = [c[0] for c in cur.description]
            data = [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.exception("Failed to load filtered inventory rows.")
            raise HTTPException(
                status_code=500,
                detail={"message": "Failed to load rows."},
            ) from e

    return {
        "items": data,
        "page_count": len(data),
        "total_count": total_count,
        "limit": int(limit),
        "offset": int(offset),
        "count": total_count,
    }
