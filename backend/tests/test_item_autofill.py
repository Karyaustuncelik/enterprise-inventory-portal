from fastapi import HTTPException

import main


def test_prepare_payload_params_fills_name_surname_from_user_name(monkeypatch):
    monkeypatch.setattr(main, "resolve_display_name", lambda username, current=None: "John Smith")
    payload = main.HardwareCreate(
        Name_Surname=None,
        Hardware_Serial_Number="SER123",
        Asset_Number="AST123",
        Country="TR",
        User_Name="EXAMPLE\\jsmith",
    )

    data, params = main._prepare_payload_params(payload)

    assert data["Name_Surname"] == "John Smith"
    assert params[2] == "John Smith"


def test_prepare_payload_params_rejects_missing_name_when_user_name_not_provided():
    payload = main.HardwareCreate(
        Name_Surname=None,
        Hardware_Serial_Number="SER123",
        Asset_Number="AST123",
        Country="TR",
        User_Name=None,
    )

    try:
        main._prepare_payload_params(payload)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Name_Surname" in exc.detail["message"]
    else:
        raise AssertionError("Expected HTTPException for missing Name_Surname")
