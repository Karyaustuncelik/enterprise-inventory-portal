import uuid

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
    return client


def test_get_charts_returns_items(monkeypatch):
    client = _build_authenticated_client(monkeypatch)
    sample = {
        "id": "chart-1",
        "title": "",
        "groupBy": "Country",
        "groupFilterValue": "TR+JO",
        "metric": "count",
        "filterBy": "none",
        "filterValue": "",
    }

    def fake_fetch():
        return [sample]

    monkeypatch.setattr(main, "_fetch_charts", fake_fetch)
    response = client.get("/charts")
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["id"] == sample["id"]
    assert payload["items"][0]["groupBy"] == sample["groupBy"]
    assert payload["items"][0]["groupFilterValue"] == sample["groupFilterValue"]


def test_post_charts_generates_id(monkeypatch):
    client = _build_authenticated_client(monkeypatch)
    captured = {}

    def fake_insert(chart):
        captured.update(chart)
        return chart

    monkeypatch.setattr(main, "_insert_chart", fake_insert)
    payload = {
        "title": "",
        "groupBy": "Country",
        "groupFilterValue": "TR+JO",
        "metric": "count",
        "filterBy": "none",
        "filterValue": "",
    }
    response = client.post("/charts", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == captured["id"]
    assert str(uuid.UUID(data["id"])) == data["id"]
    assert data["metric"] == "count"
    assert data["groupFilterValue"] == "TR+JO"


def test_post_charts_invalid_metric_returns_400(monkeypatch):
    client = _build_authenticated_client(monkeypatch)
    payload = {
        "title": "",
        "groupBy": "Country",
        "groupFilterValue": "",
        "metric": "avg",
        "filterBy": "none",
        "filterValue": "",
    }
    response = client.post("/charts", json=payload)
    assert response.status_code == 400
    assert "metric" in response.json()["message"].lower()


def test_put_charts_not_found(monkeypatch):
    client = _build_authenticated_client(monkeypatch)
    missing_id = str(uuid.uuid4())

    def fake_update(chart_id, chart):
        assert chart_id == missing_id
        return None

    monkeypatch.setattr(main, "_update_chart", fake_update)
    payload = {
        "title": "",
        "groupBy": "Country",
        "groupFilterValue": "TR",
        "metric": "count",
        "filterBy": "none",
        "filterValue": "",
    }
    response = client.put(f"/charts/{missing_id}", json=payload)
    assert response.status_code == 404


def test_delete_chart_returns_204(monkeypatch):
    client = _build_authenticated_client(monkeypatch)
    chart_id = str(uuid.uuid4())

    def fake_delete(chart_id):
        return True

    monkeypatch.setattr(main, "_delete_chart", fake_delete)
    response = client.delete(f"/charts/{chart_id}")
    assert response.status_code == 204
    assert response.text == ""
