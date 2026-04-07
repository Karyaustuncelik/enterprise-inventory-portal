import main


def test_default_status_is_active_marks_disposed_inactive():
    assert main._default_status_is_active("Disposed") is False
    assert main._default_status_is_active("Disposed - retired") is False


def test_default_status_is_active_allows_active_values():
    assert main._default_status_is_active("In Inventory") is True
    assert main._default_status_is_active(None) is True
