from fastapi.testclient import TestClient

import main


def test_users_me_returns_authenticated_user():
    client = TestClient(main.app)
    sample_user = main.UserRecord(
        id=10,
    username="EXAMPLE\\unittest",
        display_name="Unit Test",
        role_id=1,
        role_name="Admin",
    )

    def fake_current_user():
        return sample_user

    main.app.dependency_overrides[main.get_current_user] = fake_current_user
    try:
        response = client.get("/users/me")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == sample_user.username
        assert data["roleId"] == sample_user.role_id
        assert data["displayName"] == sample_user.display_name
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)


def test_normalise_auth_username_accepts_domain_and_upn_forms():
    assert main._normalise_auth_username("EXAMPLE\\ilhano") == "ilhano"
    assert main._normalise_auth_username("ilhano@example.com") == "ilhano"
    assert main._normalise_auth_username(" ilhano ") == "ilhano"
