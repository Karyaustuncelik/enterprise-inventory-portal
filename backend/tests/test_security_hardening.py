from fastapi import HTTPException
from starlette.requests import Request

import database
import main


def _build_request(host: str, headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/users/me",
        "raw_path": b"/users/me",
        "query_string": b"",
        "headers": raw_headers,
        "client": (host, 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_build_connection_string_requires_required_env(monkeypatch):
    monkeypatch.delenv("DB_SERVER", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)

    try:
        database._build_connection_string()
    except RuntimeError as exc:
        assert "DB_SERVER" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected missing DB_SERVER to fail.")


def test_build_connection_string_defaults_to_encrypted_connection(monkeypatch):
    monkeypatch.setenv("DB_SERVER", "sql-host")
    monkeypatch.setenv("DB_NAME", "inventory")
    monkeypatch.setenv("DB_USER", "svc_user")
    monkeypatch.setenv("DB_PASSWORD", "svc_password")
    monkeypatch.delenv("DB_ENCRYPT", raising=False)
    monkeypatch.delenv("DB_TRUST_SERVER_CERTIFICATE", raising=False)

    conn_str = database._build_connection_string()

    assert "SERVER=sql-host;" in conn_str
    assert "DATABASE=inventory;" in conn_str
    assert "UID=svc_user;" in conn_str
    assert "PWD=svc_password;" in conn_str
    assert "Encrypt=yes;" in conn_str
    assert "TrustServerCertificate=no;" in conn_str


def test_extract_remote_user_accepts_trusted_proxy_headers():
    request = _build_request("127.0.0.1", {"X-Remote-User": r"EXAMPLE\unit"})
    settings = main.AuthSettings()

    assert main._extract_remote_user(request, settings) == r"EXAMPLE\unit"


def test_extract_remote_user_rejects_untrusted_proxy_headers():
    request = _build_request("10.10.10.10", {"X-Remote-User": r"EXAMPLE\unit"})
    settings = main.AuthSettings()

    assert main._extract_remote_user(request, settings) is None


def test_rows_does_not_leak_internal_query_details(monkeypatch):
    class BrokenCursor:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("sensitive sql detail")

    class BrokenConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return BrokenCursor()

    monkeypatch.setattr(main, "get_conn", lambda: BrokenConnection())

    try:
        main.rows(if_deleted=0, age_min=0, age_max=1000, limit=100, offset=0)
    except HTTPException as exc:
        assert exc.status_code == 500
        assert exc.detail == {"message": "Failed to load rows."}
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected rows() failure to raise HTTPException.")
