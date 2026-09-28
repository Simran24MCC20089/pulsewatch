from models import Monitor
from services.checker import CheckResult, record_check
from tests.conftest import make_monitor


def test_public_status_hides_private(client, app):
    with app.app_context():
        public = make_monitor(name="Website", url="https://example.com/pub", is_public=True)
        private = make_monitor(name="Internal API", url="https://example.com/priv", is_public=False)
        record_check(public, CheckResult(True, http_status=200, response_ms=245))
        record_check(private, CheckResult(True, http_status=200, response_ms=12))

    page = client.get("/status")
    assert page.status_code == 200
    assert b"Website" in page.data
    assert b"Internal API" not in page.data
    assert b"All Systems Operational" in page.data or b"Operational" in page.data

    api = client.get("/api/public/status")
    assert api.status_code == 200
    payload = api.get_json()
    names = [s["name"] for s in payload["services"]]
    assert "Website" in names
    assert "Internal API" not in names
    assert payload["overall_status"] in ("operational", "degraded", "down")
    blob = api.get_data(as_text=True)
    assert "PULSEWATCH_PASSWORD" not in blob
    assert "SECRET" not in blob


def test_public_service_detail_and_404_for_private(client, app):
    with app.app_context():
        public = make_monitor(name="Public API", url="https://example.com/ok", is_public=True)
        private = make_monitor(name="Secret", url="https://example.com/secret", is_public=False)
        record_check(public, CheckResult(True, http_status=200, response_ms=180))
        pub_id, priv_id = public.id, private.id

    ok = client.get(f"/status/service/{pub_id}")
    assert ok.status_code == 200
    assert b"Public API" in ok.data
    assert b"admin" not in ok.data.lower() or b"Administrator" not in ok.data

    hidden = client.get(f"/status/service/{priv_id}")
    assert hidden.status_code == 404


def test_overall_status_down(client, app):
    with app.app_context():
        monitor = make_monitor(name="Website", is_public=True)
        record_check(monitor, CheckResult(False, http_status=500, error_type="unexpected_status", error_message="down"))

    api = client.get("/api/public/status")
    assert api.get_json()["overall_status"] == "down"


def test_dashboard_uses_real_metrics(admin_client, app):
    with app.app_context():
        monitor = make_monitor(name="Metrics Source", is_public=True)
        record_check(monitor, CheckResult(True, http_status=200, response_ms=200))

    page = admin_client.get("/dashboard")
    assert page.status_code == 200
    assert b"Metrics Source" in page.data
    assert b"Monitored Services" in page.data


def test_search_filter(admin_client, app):
    with app.app_context():
        make_monitor(name="Alpha", url="https://example.com/a")
        make_monitor(name="Beta", url="https://example.com/b", last_status="DOWN")

    found = admin_client.get("/monitors?q=Alpha")
    assert b"Alpha" in found.data
    assert b"Beta" not in found.data

    down = admin_client.get("/monitors?status=DOWN")
    assert b"Beta" in down.data
