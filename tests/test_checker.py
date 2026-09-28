from requests.exceptions import Timeout

from services.checker import execute_http_check


def test_execute_http_check_success(app, monkeypatch):
    class DummyRaw:
        def read(self, n):
            return b"ok"

    class DummyResponse:
        status_code = 200
        is_redirect = False
        headers = {}
        raw = DummyRaw()
        elapsed = type("Elapsed", (), {"total_seconds": lambda self: 0.1})()

        def close(self):
            return None

    monkeypatch.setattr(
        "services.checker.requests.get",
        lambda *a, **k: DummyResponse()
    )

    result = execute_http_check("https://example.com", 5, 200)

    assert result.is_up is True
    assert result.http_status == 200
    assert result.response_ms is not None


def test_execute_http_check_timeout(monkeypatch):
    def boom(*a, **k):
        raise Timeout()

    monkeypatch.setattr("services.checker.requests.get", boom)

    result = execute_http_check("https://example.com", 1, 200)

    assert result.is_up is False
    assert result.error_type == "timeout"


def test_manual_check_route(admin_client, app):
    from tests.conftest import make_monitor

    with app.app_context():
        monitor = make_monitor(name="Manual")
        monitor_id = monitor.id

    response = admin_client.post(
        f"/monitors/{monitor_id}/check",
        follow_redirects=True
    )

    assert response.status_code == 200
    assert (
        b"UP" in response.data
        or b"DOWN" in response.data
        or b"health" in response.data.lower()
    )