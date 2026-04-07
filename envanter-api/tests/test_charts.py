from fastapi.testclient import TestClient

import main


def test_get_charts_returns_items(monkeypatch):
    client = TestClient(main.app)
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
    client = TestClient(main.app)
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
    assert data["id"].startswith("chart-")
    assert data["metric"] == "count"
    assert data["groupFilterValue"] == "TR+JO"


def test_post_charts_invalid_metric_returns_400():
    client = TestClient(main.app)
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
    client = TestClient(main.app)

    def fake_update(chart_id, chart):
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
    response = client.put("/charts/chart-missing", json=payload)
    assert response.status_code == 404


def test_delete_chart_returns_204(monkeypatch):
    client = TestClient(main.app)

    def fake_delete(chart_id):
        return True

    monkeypatch.setattr(main, "_delete_chart", fake_delete)
    response = client.delete("/charts/chart-1")
    assert response.status_code == 204
    assert response.text == ""
