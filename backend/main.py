# main.py

import logging
import os
import re
import uuid
import json
import ipaddress
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Query, Request, Response, status
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
    enforce_trusted_proxy_ips: bool = True
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
        enforce_trusted_proxy_ips=_get_env_bool("AUTH_ENFORCE_TRUSTED_PROXY_IPS", True),
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

    @property
    def is_viewer(self) -> bool:
        role_name = (self.role_name or "").strip().lower()
        return self.role_id == 3 or role_name == "view"


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
    "brand-red",
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
    trust_remote_headers = trusted_proxy_client or not settings.enforce_trusted_proxy_ips
    if trust_remote_headers:
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


async def require_editor(user: UserRecord = Depends(get_current_user)) -> UserRecord:
    if user.is_viewer:
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


@users_router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    _: UserRecord = Depends(require_admin),
) -> Response:
    deleted = _delete_user(user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"User with id {user_id} not found."},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@users_router.get("/directory/search", response_model=List[DirectoryUserResponse])
async def directory_search(
    q: Optional[str] = Query(None, min_length=2, max_length=128),
    prefix: Optional[str] = Query(None, alias="Prefix", min_length=2, max_length=128),
    legacy_prefix: Optional[str] = Query(None, alias="prefix", min_length=2, max_length=128),
    _: UserRecord = Depends(require_editor),
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
    _: UserRecord = Depends(require_editor),
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

class ChatRequest(CamelModel):
    question: str = Field(..., min_length=2, max_length=500)


class ChatResponse(CamelModel):
    answer: str
    data: Optional[Dict[str, Any]] = None


_CHAT_LAPTOP_TYPES = ("LAPTOP", "NOTEBOOK")
_GREETINGS = ("merhaba", "selam", "hello", "hi", "naber", "nasilsin", "nasil", "nasilsiniz")


def _extract_asset_number(text: str) -> Optional[str]:
    match = re.search(r"\b([A-Za-z0-9_-]{4,})\b", text)
    return match.group(1) if match else None


def _extract_name_for_user_search(text: str) -> Optional[str]:
    lowered = text.lower()
    stop_words = {
        "bir",
        "kullanici",
        "user",
        "var",
        "mi",
        "mu",
        "varmi",
        "varmu",
        "var mi",
        "var mu",
        "isimli",
        "adli",
    }
    tokens = re.findall(r"\w+", lowered, flags=re.UNICODE)
    filtered = [tok for tok in tokens if tok not in stop_words]
    if not filtered:
        return None
    candidate = filtered[0]
    return candidate.strip()


def _parse_country_from_text(text: str) -> Optional[str]:
    lowered = text.lower()
    for key in ("turkiye", "turkey", "tr"):
        if key in lowered:
            return "TR"
    return None


def _parse_chat_intent(text: str) -> Optional[Dict[str, Any]]:
    lowered = text.lower()
    normalised = (
        lowered.replace("Ä±", "i")
        .replace("ÅŸ", "s")
        .replace("ÄŸ", "g")
        .replace("Ã§", "c")
        .replace("Ã¶", "o")
        .replace("Ã¼", "u")
    )

    if any(greet in lowered or greet in normalised for greet in _GREETINGS):
        return {"type": "greeting"}

    if "laptop" in normalised and ("toplam" in normalised or "kac" in normalised):
        country = _parse_country_from_text(lowered)
        if country:
            return {"type": "count_laptops_country", "country": country}
        return {"type": "count_laptops"}

    if "asset" in normalised and ("kimde" in normalised or "kimin" in normalised or "kim" in normalised):
        asset = _extract_asset_number(text)
        return {"type": "asset_holder", "asset": asset}

    if "laptop" in normalised:
        name = _extract_name_for_user_search(text)
        if name:
            return {"type": "user_laptop_count", "name": name}

    if "kullanici" in normalised or "user" in normalised:
        name = _extract_name_for_user_search(text)
        if name:
            return {"type": "user_exists", "name": name}

    if "departman" in normalised or "department" in normalised:
        name = _extract_name_for_user_search(text)
        if name:
            return {"type": "user_department", "name": name}

    # Generic fallback: if a name-like token is present, try to summarise that user
    name = _extract_name_for_user_search(text)
    if name:
        return {"type": "user_summary", "name": name}

    return None

chat_router = APIRouter(tags=["Chat"])


@chat_router.post("/chat", response_model=ChatResponse)
def chat_endpoint(payload: ChatRequest) -> ChatResponse:
    intent = _parse_chat_intent(payload.question)
    if not intent:
        return ChatResponse(
            answer="I do not support that question right now."
        )

    with get_conn() as conn:
        cur = conn.cursor()
        if intent["type"] == "greeting":
            return ChatResponse(answer="Hello! You can ask a question about the inventory.")

        if intent["type"] == "count_laptops":
            cur.execute(
                """
                SELECT COUNT(*) FROM [dbo].[ITHardware]
                WHERE UPPER(LTRIM(RTRIM([Hardware_Type]))) IN (?, ?)
                  AND ISNULL([If_Deleted], 0) = 0
                """,
                *_CHAT_LAPTOP_TYPES,
            )
            count = int(cur.fetchone()[0])
            return ChatResponse(answer=f"There are {count} laptops in total.", data={"count": count})

        if intent["type"] == "count_laptops_country":
            country = _normalise_country_code(intent.get("country"))
            cur.execute(
                """
                SELECT COUNT(*) FROM [dbo].[ITHardware]
                WHERE UPPER(LTRIM(RTRIM([Hardware_Type]))) IN (?, ?)
                  AND UPPER(LTRIM(RTRIM([Country]))) = ?
                  AND ISNULL([If_Deleted], 0) = 0
                """,
                *_CHAT_LAPTOP_TYPES,
                country,
            )
            count = int(cur.fetchone()[0])
            return ChatResponse(
                answer=f"There are {count} laptops for {country}.",
                data={"country": country, "count": count},
            )

        if intent["type"] == "asset_holder":
            asset = intent.get("asset")
            if not asset:
                raise HTTPException(status_code=400, detail={"message": "Asset number could not be determined."})
            cur.execute(
                """
                SELECT TOP 1 Asset_Number, Name_Surname, User_Name, Hardware_Type, Status, Country
                FROM [dbo].[ITHardware]
                WHERE Asset_Number = ?
                """,
                asset,
            )
            row = cur.fetchone()
            if not row:
                return ChatResponse(answer=f"Asset number {asset} was not found.", data={"asset": asset})
            asset_number, name_surname, user_name, hw_type, status_value, country = row
            holder = name_surname or user_name or "unknown"
            answer = (
                f"Asset {asset_number} ({hw_type}) is currently assigned to {holder} "
                f"(status: {status_value})."
            )
            return ChatResponse(
                answer=answer,
                data={
                    "asset": asset_number,
                    "holder": holder,
                    "status": status_value,
                    "country": country,
                    "type": hw_type,
                },
            )

        if intent["type"] == "user_laptop_count":
            name = intent.get("name")
            if not name:
                return ChatResponse(answer="Which user should I check laptops for?")
            cur.execute(
                """
                SELECT COUNT(*) FROM [dbo].[ITHardware]
                WHERE UPPER(LTRIM(RTRIM(Name_Surname))) LIKE ?
                  AND UPPER(LTRIM(RTRIM([Hardware_Type]))) IN (?, ?)
                  AND ISNULL([If_Deleted], 0) = 0
                """,
                f"%{name.upper()}%",
                *_CHAT_LAPTOP_TYPES,
            )
            laptop_count = int(cur.fetchone()[0])
            if laptop_count == 0:
                return ChatResponse(
                    answer=f"No laptop records found for {name}.",
                    data={"name": name, "laptops": 0},
                )
            return ChatResponse(
                answer=f"There are {laptop_count} laptop records for {name}.",
                data={"name": name, "laptops": laptop_count},
            )

        if intent["type"] == "user_exists":
            name = intent.get("name")
            display_column = _get_user_roles_display_column()
            display_sql = f"[{display_column}]" if display_column else "NULL"
            cur.execute(
                f"""
                SELECT TOP 1 Username, {display_sql} AS DisplayName
                FROM [dbo].[UserRoles]
                WHERE UPPER(LTRIM(RTRIM(Username))) LIKE ?
                   OR UPPER(LTRIM(RTRIM({display_sql}))) LIKE ?
                """,
                f"%{name.upper()}%",
                f"%{name.upper()}%",
            )
            row = cur.fetchone()
            if row:
                username, display_name = row
                resolved = display_name or username
                return ChatResponse(
                    answer=f"{resolved} exists in the records.",
                    data={"username": username, "display_name": display_name or username},
                )

            # Fallback: look into hardware table by Name_Surname
            cur.execute(
                """
                SELECT TOP 1 Name_Surname, User_Name
                FROM [dbo].[ITHardware]
                WHERE UPPER(LTRIM(RTRIM(Name_Surname))) LIKE ?
            """,
                f"%{name.upper()}%",
            )
            hw_row = cur.fetchone()
            if hw_row:
                name_surname, user_name = hw_row
                holder = name_surname or user_name or name
                cur.execute(
                    """
                    SELECT COUNT(*) FROM [dbo].[ITHardware]
                    WHERE UPPER(LTRIM(RTRIM(Name_Surname))) LIKE ?
                      AND UPPER(LTRIM(RTRIM([Hardware_Type]))) IN (?, ?)
                      AND ISNULL([If_Deleted], 0) = 0
                    """,
                    f"%{name.upper()}%",
                    *_CHAT_LAPTOP_TYPES,
                )
                laptop_count = int(cur.fetchone()[0])
                return ChatResponse(
                    answer=f"{holder} exists in the records. Laptop count: {laptop_count}.",
                    data={"name": holder, "laptops": laptop_count},
                )

            return ChatResponse(answer=f"No user named {name} was found.", data={"name": name})

        if intent["type"] == "user_department":
            name = intent.get("name")
            if not name:
                return ChatResponse(answer="Which user's department should I look up?")
            cur.execute(
                """
                SELECT TOP 1 Name_Surname, Department
                FROM [dbo].[ITHardware]
                WHERE UPPER(LTRIM(RTRIM(Name_Surname))) LIKE ?
                  AND ISNULL([If_Deleted], 0) = 0
                ORDER BY Department DESC
                """,
                f"%{name.upper()}%",
            )
            row = cur.fetchone()
            if not row:
                return ChatResponse(
                    answer=f"No department information found for {name}.",
                    data={"name": name},
                )
            name_surname, department = row
            dept_value = department or "unknown"
            return ChatResponse(
                answer=f"{name_surname} department: {dept_value}.",
                data={"name": name_surname, "department": dept_value},
            )

        if intent["type"] == "user_summary":
            name = intent.get("name")
            if not name:
                return ChatResponse(answer="Which user should I look up?")
            cur.execute(
                """
                SELECT TOP 1 Name_Surname, Department, Country
                FROM [dbo].[ITHardware]
                WHERE UPPER(LTRIM(RTRIM(Name_Surname))) LIKE ?
                  AND ISNULL([If_Deleted], 0) = 0
                """,
                f"%{name.upper()}%",
            )
            row = cur.fetchone()
            if not row:
                return ChatResponse(answer=f"No records found for {name}.", data={"name": name})
            name_surname, department, country = row
            cur.execute(
                """
                SELECT
                  SUM(CASE WHEN UPPER(LTRIM(RTRIM([Hardware_Type]))) IN (?, ?) THEN 1 ELSE 0 END) AS laptop_count,
                  COUNT(*) AS total_count
                FROM [dbo].[ITHardware]
                WHERE UPPER(LTRIM(RTRIM(Name_Surname))) LIKE ?
                  AND ISNULL([If_Deleted], 0) = 0
                """,
                *_CHAT_LAPTOP_TYPES,
                f"%{name.upper()}%",
            )
            laptop_count, total_count = cur.fetchone()
            dept_value = department or "unknown"
            country_value = country or "unknown"
            answer = (
                f"{name_surname} exists in the records. Department: {dept_value}. Country: {country_value}. "
                f"Laptop count: {int(laptop_count or 0)}. Total inventory: {int(total_count or 0)}."
            )
            return ChatResponse(
                answer=answer,
                data={
                    "name": name_surname,
                    "department": dept_value,
                    "country": country_value,
                    "laptops": int(laptop_count or 0),
                    "total": int(total_count or 0),
                },
            )

    return ChatResponse(answer="I cannot answer that question right now.")


app.include_router(chat_router)


# -----------------------------
# Charts (shared)
# -----------------------------
_VALID_CHART_METRICS = {"count", "ratio"}


def _generate_chart_id() -> str:
    return str(uuid.uuid4())


def _normalise_chart_id(raw_id: Optional[str], *, allow_none: bool = True) -> Optional[str]:
    if raw_id is None:
        if allow_none:
            return None
        raise HTTPException(status_code=400, detail={"message": "id is required."})

    if not isinstance(raw_id, str) or not raw_id.strip():
        raise HTTPException(status_code=400, detail={"message": "id must be a non-empty string."})

    value = raw_id.strip()
    try:
        if value.lower().startswith("chart-"):
            return str(uuid.UUID(hex=value[6:]))
        return str(uuid.UUID(value))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail={"message": "id is invalid. Expected GUID."})


def _resolve_chart_payload(
    payload_body: Optional[Dict[str, Any]],
    payload_query: Optional[str],
) -> Dict[str, Any]:
    if payload_body is not None:
        return payload_body

    if payload_query is None:
        raise HTTPException(status_code=400, detail={"message": "Invalid JSON payload."})

    try:
        payload = json.loads(payload_query)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail={"message": "Query payload must be valid JSON."}) from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail={"message": "Query payload must be a JSON object."})
    return payload


def _require_chart_field(payload: Dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise HTTPException(
            status_code=400,
            detail={"message": f"Missing required field: {key}."},
        )
    return payload.get(key)


def _validate_chart_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail={"message": "Invalid JSON payload."})

    title = _require_chart_field(payload, "title")
    if title is not None and not isinstance(title, str):
        raise HTTPException(status_code=400, detail={"message": "title must be a string or null."})

    group_by = _require_chart_field(payload, "groupBy")
    if not isinstance(group_by, str):
        raise HTTPException(status_code=400, detail={"message": "groupBy must be a string."})

    metric = _require_chart_field(payload, "metric")
    if not isinstance(metric, str):
        raise HTTPException(status_code=400, detail={"message": "metric must be a string."})
    metric_value = metric.strip().lower()
    if metric_value not in _VALID_CHART_METRICS:
        raise HTTPException(status_code=400, detail={"message": "metric must be 'count' or 'ratio'."})

    filter_by = _require_chart_field(payload, "filterBy")
    if not isinstance(filter_by, str):
        raise HTTPException(status_code=400, detail={"message": "filterBy must be a string."})

    filter_value = _require_chart_field(payload, "filterValue")
    if not isinstance(filter_value, str):
        raise HTTPException(status_code=400, detail={"message": "filterValue must be a string."})

    group_filter_value = payload.get("groupFilterValue", "")
    if group_filter_value is None:
        group_filter_value = ""
    if not isinstance(group_filter_value, str):
        raise HTTPException(status_code=400, detail={"message": "groupFilterValue must be a string."})

    chart_id = payload.get("id")
    if chart_id is not None:
        if not isinstance(chart_id, str) or not chart_id.strip():
            raise HTTPException(status_code=400, detail={"message": "id must be a non-empty string."})
        chart_id = chart_id.strip()

    return {
        "id": chart_id,
        "title": title,
        "groupBy": group_by,
        "groupFilterValue": group_filter_value,
        "metric": metric_value,
        "filterBy": filter_by,
        "filterValue": filter_value,
    }


def _chart_response_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    raw_id = row.get("id")
    return {
        "id": str(raw_id) if raw_id is not None else None,
        "title": row.get("title") if row.get("title") is not None else "",
        "groupBy": row.get("groupBy") or "",
        "groupFilterValue": row.get("groupFilterValue") or "",
        "metric": (row.get("metric") or "").lower(),
        "filterBy": row.get("filterBy") or "",
        "filterValue": row.get("filterValue") or "",
    }


def _ensure_charts_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        IF NOT EXISTS (
            SELECT 1
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'dbo'
              AND TABLE_NAME = 'charts'
        )
        BEGIN
            CREATE TABLE [dbo].[charts] (
                [id] NVARCHAR(64) NOT NULL PRIMARY KEY,
                [title] NVARCHAR(200) NULL,
                [groupBy] NVARCHAR(100) NOT NULL,
                [groupFilterValue] NVARCHAR(400) NOT NULL
                    CONSTRAINT [DF_charts_groupFilterValue] DEFAULT (''),
                [metric] NVARCHAR(10) NOT NULL,
                [filterBy] NVARCHAR(100) NOT NULL,
                [filterValue] NVARCHAR(200) NOT NULL,
                [created_at] DATETIME2(0) NOT NULL
                    CONSTRAINT [DF_charts_created_at] DEFAULT SYSUTCDATETIME(),
                [updated_at] DATETIME2(0) NOT NULL
                    CONSTRAINT [DF_charts_updated_at] DEFAULT SYSUTCDATETIME(),
                CONSTRAINT [CK_charts_metric] CHECK ([metric] IN ('count', 'ratio'))
            );
        END;

        IF COL_LENGTH('dbo.charts', 'groupFilterValue') IS NULL
        BEGIN
            ALTER TABLE [dbo].[charts]
            ADD [groupFilterValue] NVARCHAR(400) NOT NULL
                CONSTRAINT [DF_charts_groupFilterValue] DEFAULT ('');
        END;
        """
    )
    conn.commit()


def _fetch_charts() -> List[Dict[str, Any]]:
    sql = """
        SELECT [id], [title], [groupBy], [groupFilterValue], [metric], [filterBy], [filterValue]
        FROM [dbo].[charts]
        ORDER BY [created_at] ASC, [id] ASC;
    """
    with get_conn() as conn:
        _ensure_charts_table(conn)
        cur = conn.cursor()
        cur.execute(sql)
        cols = [col[0] for col in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetch_chart_by_id(chart_id: str) -> Optional[Dict[str, Any]]:
    sql = """
        SELECT [id], [title], [groupBy], [groupFilterValue], [metric], [filterBy], [filterValue]
        FROM [dbo].[charts]
        WHERE [id] = ?;
    """
    with get_conn() as conn:
        _ensure_charts_table(conn)
        cur = conn.cursor()
        cur.execute(sql, chart_id)
        row = cur.fetchone()
        if not row:
            return None
        cols = [col[0] for col in cur.description]
        return dict(zip(cols, row))


def _insert_chart(chart: Dict[str, Any]) -> Dict[str, Any]:
    sql = """
        INSERT INTO [dbo].[charts] (
            [id], [title], [groupBy], [groupFilterValue], [metric], [filterBy], [filterValue]
        )
        VALUES (?, ?, ?, ?, ?, ?, ?);
    """
    stored: Optional[Dict[str, Any]] = None
    with get_conn() as conn:
        _ensure_charts_table(conn)
        cur = conn.cursor()
        try:
            cur.execute("SELECT 1 FROM [dbo].[charts] WHERE [id] = ?", chart["id"])
            if cur.fetchone():
                raise HTTPException(status_code=409, detail={"message": "Chart id already exists."})
            cur.execute(
                sql,
                chart["id"],
                chart["title"],
                chart["groupBy"],
                chart["groupFilterValue"],
                chart["metric"],
                chart["filterBy"],
                chart["filterValue"],
            )
            cur.execute(
                """
                SELECT [id], [title], [groupBy], [groupFilterValue], [metric], [filterBy], [filterValue]
                FROM [dbo].[charts]
                WHERE [id] = ?;
                """,
                chart["id"],
            )
            row = cur.fetchone()
            if row:
                cols = [col[0] for col in cur.description]
                stored = dict(zip(cols, row))
            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            raise
    return stored or chart


def _update_chart(chart_id: str, chart: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sql = """
        UPDATE [dbo].[charts]
        SET [title] = ?,
            [groupBy] = ?,
            [groupFilterValue] = ?,
            [metric] = ?,
            [filterBy] = ?,
            [filterValue] = ?,
            [updated_at] = SYSUTCDATETIME()
        WHERE [id] = ?;
    """
    stored: Optional[Dict[str, Any]] = None
    with get_conn() as conn:
        _ensure_charts_table(conn)
        cur = conn.cursor()
        try:
            cur.execute(
                sql,
                chart["title"],
                chart["groupBy"],
                chart["groupFilterValue"],
                chart["metric"],
                chart["filterBy"],
                chart["filterValue"],
                chart_id,
            )
            if cur.rowcount == 0:
                conn.rollback()
                return None
            cur.execute(
                """
                SELECT [id], [title], [groupBy], [groupFilterValue], [metric], [filterBy], [filterValue]
                FROM [dbo].[charts]
                WHERE [id] = ?;
                """,
                chart_id,
            )
            row = cur.fetchone()
            if row:
                cols = [col[0] for col in cur.description]
                stored = dict(zip(cols, row))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return stored


def _delete_chart(chart_id: str) -> bool:
    sql = "DELETE FROM [dbo].[charts] WHERE [id] = ?;"
    with get_conn() as conn:
        _ensure_charts_table(conn)
        cur = conn.cursor()
        try:
            cur.execute(sql, chart_id)
            deleted = cur.rowcount
            if deleted == 0:
                conn.rollback()
                return False
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return True


charts_router = APIRouter(tags=["Charts"])


@charts_router.get("/charts")
def list_charts():
    try:
        rows = _fetch_charts()
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"message": "Failed to load charts."}) from exc
    return {"items": [_chart_response_from_row(row) for row in rows]}


@charts_router.post("/charts", status_code=201)
def create_chart(
    payload: Optional[Dict[str, Any]] = Body(None),
    payload_query: Optional[str] = Query(None, alias="payload"),
    _: UserRecord = Depends(require_editor),
):
    chart_payload = _resolve_chart_payload(payload, payload_query)
    chart = _validate_chart_payload(chart_payload)
    if not chart["id"]:
        chart["id"] = _generate_chart_id()
    else:
        try:
            chart["id"] = _normalise_chart_id(chart["id"], allow_none=False)
        except HTTPException:
            # Legacy frontend may send non-GUID ids like "chart-..."; generate a backend GUID instead.
            chart["id"] = _generate_chart_id()
    try:
        created = _insert_chart(chart)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"message": "Failed to create chart."}) from exc
    return _chart_response_from_row(created)


@charts_router.put("/charts/{chart_id}")
def update_chart(
    chart_id: str,
    payload: Optional[Dict[str, Any]] = Body(None),
    payload_query: Optional[str] = Query(None, alias="payload"),
    _: UserRecord = Depends(require_editor),
):
    normalised_chart_id = _normalise_chart_id(chart_id, allow_none=False)
    chart_payload = _resolve_chart_payload(payload, payload_query)
    chart = _validate_chart_payload(chart_payload)
    if chart["id"]:
        chart["id"] = _normalise_chart_id(chart["id"], allow_none=False)
    if chart["id"] and chart["id"] != normalised_chart_id:
        raise HTTPException(status_code=400, detail={"message": "Payload id does not match URL id."})
    chart["id"] = normalised_chart_id
    try:
        updated = _update_chart(normalised_chart_id, chart)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"message": "Failed to update chart."}) from exc
    if not updated:
        raise HTTPException(status_code=404, detail={"message": "Chart not found."})
    return _chart_response_from_row(updated)


@charts_router.delete("/charts/{chart_id}", status_code=204)
def delete_chart(
    chart_id: str,
    _: UserRecord = Depends(require_editor),
):
    normalised_chart_id = _normalise_chart_id(chart_id, allow_none=False)
    try:
        deleted = _delete_chart(normalised_chart_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"message": "Failed to delete chart."}) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail={"message": "Chart not found."})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


app.include_router(charts_router)


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


def _delete_user(user_id: int) -> bool:
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM [dbo].[UserRoles]
            WHERE Id = ?
            """,
            user_id,
        )
        if cursor.rowcount == 0:
            conn.rollback()
            return False
        conn.commit()
        return True
    except Exception as exc:
        logger.error("Failed to delete user %s: %s", user_id, exc)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


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


def _is_disposed_status(value: Optional[str]) -> bool:
    return "disposed" in (value or "").strip().lower()


def _default_status_is_active(value: Optional[str]) -> bool:
    return not _is_disposed_status(value)


def _coerce_status_is_active(raw_active: Optional[object], value: Optional[str]) -> bool:
    if raw_active is None:
        return _default_status_is_active(value)
    return bool(raw_active)


def _fetch_status_is_active(conn, value: Optional[str]) -> Optional[bool]:
    if not value:
        return None
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT TOP 1 IsActive
            FROM FieldParams
            WHERE FieldName = ?
              AND UPPER(LTRIM(RTRIM(ParamName))) = UPPER(?)
            """,
            "Status",
            value,
        )
        row = cur.fetchone()
    except Exception as exc:
        logger.warning("Failed to fetch status is_active for %s: %s", value, exc)
        return None
    if not row:
        return None
    return None if row[0] is None else bool(row[0])


def _resolve_if_deleted(conn, status_value: Optional[str], explicit_flag: Optional[int]) -> int:
    if status_value:
        is_active = _fetch_status_is_active(conn, status_value)
        if is_active is None:
            is_active = _default_status_is_active(status_value)
        return 0 if is_active else 1
    return 1 if explicit_flag else 0


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


def _prepare_payload_params(payload, conn=None):
    data = _prepare_payload_dict(payload)
    if not data.get("Name_Surname") and data.get("User_Name"):
        resolved_name = _clean_text(resolve_display_name(data["User_Name"]))
        if resolved_name:
            data["Name_Surname"] = resolved_name
    if conn is not None:
        data["If_Deleted"] = _resolve_if_deleted(conn, data.get("Status"), data.get("If_Deleted"))
    if not data.get("Name_Surname"):
        raise HTTPException(
            status_code=400,
            detail={"message": "Name_Surname is required when it cannot be derived from User_Name."},
        )
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
    "name_surname": ("[Name_Surname]", "word_prefix_like"),
    "identity": ("[Identity]", "like"),
    # Department yalnÄ±zca kod kÄ±smÄ±na gÃ¶re filtrelensin
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
    "Name_Surname": ("[Name_Surname]", "word_prefix_like"),
    "Identity": ("[Identity]", "like"),
    # Global column search'ta da Department kodu baz alÄ±nsÄ±n
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

def _build_searchable_column_lookup(columns: Dict[str, Tuple[str, str]]) -> Dict[str, Tuple[str, str]]:
    lookup: Dict[str, Tuple[str, str]] = {}
    for key, value in columns.items():
        lowered = key.lower()
        collapsed = re.sub(r"[\s_\-./\\]+", "", lowered)
        space_normalized = re.sub(r"[\s_\-./\\]+", " ", lowered).strip()
        for alias in (lowered, space_normalized, collapsed):
            if alias:
                lookup[alias] = value
    return lookup


SEARCHABLE_COLUMN_LOOKUP = _build_searchable_column_lookup(SEARCHABLE_COLUMNS)

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
    is_active: Optional[bool] = None


class FieldParametersResponse(BaseModel):
    fields: Dict[str, List[FieldParamItem]]


class FieldParamCreate(BaseModel):
    value: str = Field(..., min_length=1, max_length=255)
    is_active: Optional[bool] = None

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
    is_active: Optional[bool] = None

    @field_validator("original", "value")
    def normalise_update_values(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("Value cannot be empty.")
        return value


class FieldParamPathUpdate(BaseModel):
    original: Optional[str] = Field(None, min_length=1, max_length=255)
    value: Optional[str] = Field(None, min_length=1, max_length=255)
    update_existing: bool = True
    is_active: Optional[bool] = None

    @field_validator("original", "value")
    def normalise_optional_update_values(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
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
    status_active_map: Dict[str, bool] = {}
    cur = conn.cursor()
    if canonical == "Status":
        cur.execute(
            "SELECT ParamName, IsActive FROM FieldParams WHERE FieldName = ? ORDER BY ParamName ASC",
            canonical,
        )
        for raw_value, raw_active in cur.fetchall():
            value = (raw_value or "").strip()
            if value and value not in managed_values:
                managed_values.append(value)
                status_active_map[value] = _coerce_status_is_active(raw_active, value)
    else:
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
        item = {"value": value, "usage_count": usage, "managed": True}
        if canonical == "Status":
            item["is_active"] = status_active_map.get(value, _default_status_is_active(value))
        items.append(item)
        seen.add(value)
    for value, usage in usage_counts.items():
        if value not in seen:
            item = {"value": value, "usage_count": usage, "managed": False}
            if canonical == "Status":
                item["is_active"] = _default_status_is_active(value)
            items.append(item)
    items.sort(key=lambda item: (0 if item.get("managed") else 1, item["value"].lower()))
    return items


TEXT_SEARCH_COLLATION = "Turkish_100_CI_AI"
NULL_FILTER_TOKEN = "__NULL_FILTER__"
TEXT_SEARCH_SQL_SEPARATORS = ("_", "-", "/", "\\", ".", ",", ";", ":")
TEXT_SEARCH_TRANSLATION = str.maketrans(
    {separator: " " for separator in TEXT_SEARCH_SQL_SEPARATORS} | {"\t": " "}
)


def _split_text_search_terms(value: object) -> List[str]:
    if value is None:
        return []
    normalised = str(value).translate(TEXT_SEARCH_TRANSLATION)
    return [segment for segment in normalised.strip().split() if segment]


def _build_text_search_expr(column_sql: str) -> str:
    text_expr = f"CAST({column_sql} AS nvarchar(max)) COLLATE {TEXT_SEARCH_COLLATION}"
    for separator in TEXT_SEARCH_SQL_SEPARATORS:
        text_expr = f"REPLACE({text_expr}, '{separator}', ' ')"
    return f"LTRIM(RTRIM({text_expr}))"


def _append_word_prefix_filter(clauses, params, column_sql, raw_value):
    search_terms = _split_text_search_terms(raw_value)
    if not search_terms:
        return
    text_expr = _build_text_search_expr(column_sql)
    clauses.append(
        "(" + " AND ".join([f"({text_expr} LIKE ? OR {text_expr} LIKE ?)" for _ in search_terms]) + ")"
    )
    for term in search_terms:
        params.extend([f"{term}%", f"% {term}%"])


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
        text_expr = _build_text_search_expr(column_sql)
        # Trim + upper ile saÄŸlamlaÅŸtÄ±r
        clauses.append("(" + " AND ".join([f"{text_expr} LIKE ?" for _ in search_terms]) + ")")
        params.extend([f"%{term}%" for term in search_terms])

    elif operator == "word_prefix_like":
        _append_word_prefix_filter(clauses, params, column_sql, value)

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
# server ve db ayakta mÄ±?
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

@app.get("/field-parameters", response_model=FieldParametersResponse, response_model_exclude_none=True)
def list_field_parameters():
    with get_conn() as conn:
        fields = {field: _fetch_field_params(conn, field) for field in CHOICE_FIELDS}
    return {"fields": fields}


@app.get("/field-parameters/{field}", response_model=List[FieldParamItem], response_model_exclude_none=True)
def get_field_parameters(field: str):
    canonical = _ensure_choice_field(field)
    with get_conn() as conn:
        return _fetch_field_params(conn, canonical)


@app.post("/field-parameters/{field}", response_model=FieldParamItem, status_code=201, response_model_exclude_none=True)
def create_field_parameter(
    field: str,
    payload: FieldParamCreate,
    _: UserRecord = Depends(require_admin),
):
    canonical = _ensure_choice_field(field)
    value = payload.value
    if canonical == "Country" and len(value) != 2:
        raise HTTPException(status_code=400, detail={"message": "Country values must be exactly 2 characters."})
    is_status = canonical == "Status"
    is_active = None
    if is_status:
        if payload.is_active is None:
            is_active = _default_status_is_active(value)
        else:
            is_active = bool(payload.is_active)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM FieldParams WHERE FieldName = ? AND UPPER(LTRIM(RTRIM(ParamName))) = UPPER(?)",
            canonical,
            value,
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="This value already exists for the selected field.")
        if is_status:
            cur.execute(
                "INSERT INTO FieldParams (FieldName, ParamName, IsActive) VALUES (?, ?, ?)",
                canonical,
                value,
                1 if is_active else 0,
            )
        else:
            cur.execute("INSERT INTO FieldParams (FieldName, ParamName) VALUES (?, ?)", canonical, value)
        conn.commit()
        usage_count = _get_usage_count(conn, canonical, value)
    item = {"value": value, "usage_count": usage_count, "managed": True}
    if is_status:
        item["is_active"] = is_active
    return item


@app.put("/field-parameters/{field}", response_model=FieldParamItem, response_model_exclude_none=True)
@app.patch("/field-parameters/{field}", response_model=FieldParamItem, response_model_exclude_none=True)
def update_field_parameter(
    field: str,
    payload: FieldParamUpdate,
    _: UserRecord = Depends(require_admin),
):
    canonical = _ensure_choice_field(field)
    original = payload.original
    new_value = payload.value
    if canonical == "Country" and len(new_value) != 2:
        raise HTTPException(status_code=400, detail={"message": "Country values must be exactly 2 characters."})
    is_status = canonical == "Status"
    same_value = new_value.lower() == original.lower()
    new_is_active: Optional[bool] = None
    with get_conn() as conn:
        cur = conn.cursor()
        if is_status:
            cur.execute(
                "SELECT ParamName, IsActive FROM FieldParams WHERE FieldName = ? AND UPPER(LTRIM(RTRIM(ParamName))) = UPPER(?)",
                canonical,
                original,
            )
        else:
            cur.execute(
                "SELECT ParamName FROM FieldParams WHERE FieldName = ? AND UPPER(LTRIM(RTRIM(ParamName))) = UPPER(?)",
                canonical,
                original,
            )
        row = cur.fetchone()
        if not row:
            if is_status and payload.is_active is not None and same_value:
                cur.execute(
                    "SELECT ParamName, IsActive FROM FieldParams WHERE FieldName = ? AND UPPER(LTRIM(RTRIM(ParamName))) = UPPER(?)",
                    canonical,
                    new_value,
                )
                row = cur.fetchone()
                if not row:
                    new_is_active = bool(payload.is_active)
                    cur.execute(
                        "INSERT INTO FieldParams (FieldName, ParamName, IsActive) VALUES (?, ?, ?)",
                        canonical,
                        new_value,
                        1 if new_is_active else 0,
                    )
                    column_sql = _field_column_sql(canonical)
                    trim_expr = f"LTRIM(RTRIM({column_sql}))"
                    cur.execute(
                        f"UPDATE [dbo].[ITHardware] SET [If_Deleted] = ? WHERE {trim_expr} = ?",
                        0 if new_is_active else 1,
                        new_value.strip(),
                    )
                    conn.commit()
                    usage_count = _get_usage_count(conn, canonical, new_value)
                    item = {"value": new_value, "usage_count": usage_count, "managed": True, "is_active": new_is_active}
                    return item
            if not row:
                raise HTTPException(status_code=404, detail="The specified value was not found.")
        stored_original = row[0]
        current_is_active = None
        if is_status:
            raw_active = row[1]
            current_is_active = None if raw_active is None else bool(raw_active)
        if not same_value:
            cur.execute(
                "SELECT 1 FROM FieldParams WHERE FieldName = ? AND UPPER(LTRIM(RTRIM(ParamName))) = UPPER(?)",
                canonical,
                new_value,
            )
            existing = cur.fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="Another parameter already uses this value.")
        if is_status:
            requested_is_active = payload.is_active
            if requested_is_active is None:
                new_is_active = current_is_active
                if new_is_active is None:
                    new_is_active = _default_status_is_active(new_value)
            else:
                new_is_active = bool(requested_is_active)
            cur.execute(
                "UPDATE FieldParams SET ParamName = ?, IsActive = ? WHERE FieldName = ? AND ParamName = ?",
                new_value,
                1 if new_is_active else 0,
                canonical,
                stored_original,
            )
        else:
            cur.execute(
                "UPDATE FieldParams SET ParamName = ? WHERE FieldName = ? AND ParamName = ?",
                new_value,
                canonical,
                stored_original,
            )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Value update failed.")
        if payload.update_existing and not same_value:
            column_sql = _field_column_sql(canonical)
            trim_expr = f"LTRIM(RTRIM({column_sql}))"
            cur.execute(
                f"UPDATE [dbo].[ITHardware] SET {column_sql} = ? WHERE {trim_expr} = ?",
                new_value,
                stored_original.strip(),
            )
        if is_status and payload.is_active is not None and new_is_active != current_is_active:
            column_sql = _field_column_sql(canonical)
            trim_expr = f"LTRIM(RTRIM({column_sql}))"
            status_value_for_items = (
                new_value
                if (payload.update_existing and not same_value)
                else stored_original.strip()
            )
            cur.execute(
                f"UPDATE [dbo].[ITHardware] SET [If_Deleted] = ? WHERE {trim_expr} = ?",
                0 if new_is_active else 1,
                status_value_for_items,
            )
        conn.commit()
        usage_count = _get_usage_count(conn, canonical, new_value)
    item = {"value": new_value, "usage_count": usage_count, "managed": True}
    if is_status:
        item["is_active"] = new_is_active
    return item


@app.put("/field-parameters/{field}/{value}", response_model=FieldParamItem, response_model_exclude_none=True)
@app.patch("/field-parameters/{field}/{value}", response_model=FieldParamItem, response_model_exclude_none=True)
def update_field_parameter_by_value(
    field: str,
    value: str,
    payload: FieldParamPathUpdate,
    current_user: UserRecord = Depends(require_admin),
):
    payload_original = payload.original or value
    payload_value = payload.value or value
    merged_payload = FieldParamUpdate(
        original=payload_original,
        value=payload_value,
        update_existing=payload.update_existing,
        is_active=payload.is_active,
    )
    return update_field_parameter(field, merged_payload, current_user)


@app.delete("/field-parameters/{field}/{value}")
def delete_field_parameter(
    field: str,
    value: str,
    force: bool = Query(False),
    replacement: Optional[str] = Query(None),
    _: UserRecord = Depends(require_admin),
):
    canonical = _ensure_choice_field(field)
    target_value = _normalise_param_value(value)
    is_status = canonical == "Status"
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
                if is_status:
                    cur.execute(
                        "SELECT ParamName, IsActive FROM FieldParams WHERE FieldName = ? AND RTRIM(LTRIM(ParamName)) = ?",
                        canonical,
                        replacement_value,
                    )
                else:
                    cur.execute(
                        "SELECT ParamName FROM FieldParams WHERE FieldName = ? AND RTRIM(LTRIM(ParamName)) = ?",
                        canonical,
                        replacement_value,
                    )
                rep_row = cur.fetchone()
                if not rep_row:
                    raise HTTPException(status_code=404, detail="Replacement value is not registered.")
                applied_replacement = rep_row[0].strip()
                replacement_active = None
                if is_status:
                    raw_active = rep_row[1]
                    replacement_active = _coerce_status_is_active(raw_active, applied_replacement)
                if applied_replacement.lower() == stored_value.strip().lower():
                    raise HTTPException(status_code=400, detail="Replacement must be different from the removed value.")
                if is_status:
                    cur.execute(
                        f"UPDATE [dbo].[ITHardware] SET {column_sql} = ?, [If_Deleted] = ? WHERE {trim_expr} = ?",
                        applied_replacement,
                        0 if replacement_active else 1,
                        stored_value.strip(),
                    )
                else:
                    cur.execute(
                        f"UPDATE [dbo].[ITHardware] SET {column_sql} = ? WHERE {trim_expr} = ?",
                        applied_replacement,
                        stored_value.strip(),
                    )
                affected = cur.rowcount
            elif force:
                if is_status:
                    cur.execute(
                        f"UPDATE [dbo].[ITHardware] SET {column_sql} = NULL, [If_Deleted] = 0 WHERE {trim_expr} = ?",
                        stored_value.strip(),
                    )
                else:
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
# Yeni kayÄ±t oluÅŸturma (POST)
# -----------------------------
class HardwareCreate(BaseModel):
    Name_Surname: Optional[str] = Field(None, max_length=50)
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
def create_item(
    payload: HardwareCreate,
    _: UserRecord = Depends(require_editor),
):
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

    with get_conn() as conn:
        cleaned, params = _prepare_payload_params(payload, conn)
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
def update_item(
    item_ref: str,
    payload: HardwareCreate,
    _: UserRecord = Depends(require_editor),
):
    reference = _clean_text(item_ref)
    if not reference:
        raise HTTPException(status_code=400, detail="Invalid item reference.")
    with get_conn() as conn:
        cleaned, params = _prepare_payload_params(payload, conn)
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
def delete_item(
    item_ref: str,
    _: UserRecord = Depends(require_editor),
):
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
# Ãœlke bazÄ±nda spare oranlarÄ±
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
        if key == "if_deleted":
            # Active/Inactive inventory pages still send if_deleted=0/1 for compatibility,
            # but page membership is determined by Status button state (FieldParams.IsActive),
            # not the potentially stale ITHardware.If_Deleted column.
            continue
        add_filter(column_sql, operator, filter_values.get(key))

    if if_deleted is not None:
        # Compatibility mapping:
        #   if_deleted=0 -> statuses marked active in FieldParams
        #   if_deleted=1 -> statuses marked inactive in FieldParams
        desired_status_is_active = 0 if int(if_deleted) == 1 else 1
        status_trim_expr = "LTRIM(RTRIM(ISNULL([Status], '')))"
        status_is_active_expr = f"""
            COALESCE(
                (
                    SELECT TOP 1
                        CASE
                            WHEN fp.IsActive IS NULL THEN NULL
                            WHEN fp.IsActive = 1 THEN 1
                            ELSE 0
                        END
                    FROM FieldParams fp
                    WHERE fp.FieldName = 'Status'
                      AND UPPER(LTRIM(RTRIM(fp.ParamName))) = UPPER({status_trim_expr})
                ),
                CASE
                    WHEN LOWER({status_trim_expr}) LIKE '%disposed%' THEN 0
                    ELSE 1
                END
            )
        """
        where_clauses.append(f"({status_is_active_expr}) = ?")
        params.append(desired_status_is_active)

    search_key = (column or "").strip().lower()
    search_value = (search or "").strip()
    if search_value and search_key:
        lookup_key = search_key
        search_column_info = SEARCHABLE_COLUMN_LOOKUP.get(lookup_key)
        if not search_column_info:
            search_column_info = SEARCHABLE_COLUMN_LOOKUP.get(
                re.sub(r"[\s_\-./\\]+", " ", lookup_key).strip()
            )
        if not search_column_info:
            search_column_info = SEARCHABLE_COLUMN_LOOKUP.get(
                re.sub(r"[\s_\-./\\]+", "", lookup_key)
            )
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

