from fastapi.testclient import TestClient

import main


def _build_authenticated_client(monkeypatch):
    sample_user = main.UserRecord(
        id=10,
        username="EXAMPLE\\unittest",
        display_name="Unit Test",
        role_id=1,
        role_name="Admin",
    )

    monkeypatch.setenv("AUTH_TRUSTED_PROXY_IPS", "testclient")
    main.get_auth_settings.cache_clear()
    monkeypatch.setattr(main, "_fetch_user_by_username", lambda _username: sample_user)

    client = TestClient(main.app)
    client.headers.update({"X-Remote-User": sample_user.username})
    return client, sample_user


def test_users_me_returns_authenticated_user(monkeypatch):
    client, sample_user = _build_authenticated_client(monkeypatch)

    response = client.get("/users/me")
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == sample_user.username
    assert data["roleId"] == sample_user.role_id
    assert data["displayName"] == sample_user.display_name


def test_normalise_auth_username_accepts_domain_and_upn_forms():
    assert main._normalise_auth_username("EXAMPLE\\ilhano") == "ilhano"
    assert main._normalise_auth_username("ilhano@example.com") == "ilhano"
    assert main._normalise_auth_username(" ilhano ") == "ilhano"
