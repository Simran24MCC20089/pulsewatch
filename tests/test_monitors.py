from models import Incident, Monitor, Recommendation
from services.checker import CheckResult, record_check
from services.recommendations import generate_recommendations
from tests.conftest import make_monitor


def test_create_edit_delete_monitor(admin_client, app):
    created = admin_client.post(
        "/monitors",
        data={
            "name": "Example API",
            "url": "https://example.com/api",
            "interval_seconds": "30",
            "timeout_seconds": "5",
            "expected_status": "200",
            "visibility": "public",
        },
        follow_redirects=True,
    )
    assert created.status_code == 200

    with app.app_context():
        monitor = Monitor.query.filter_by(name="Example API").first()
        assert monitor is not None
        monitor_id = monitor.id

    edited = admin_client.post(
        f"/monitors/{monitor_id}/edit",
        data={
            "name": "Example API",
            "url": "https://example.com/v2",
            "interval_seconds": "45",
            "timeout_seconds": "8",
            "expected_status": "201",
            "visibility": "private",
        },
        follow_redirects=True,
    )
    assert edited.status_code == 200
    with app.app_context():
        monitor = db_monitor(monitor_id)
        assert monitor.url.endswith("/v2")
        assert monitor.interval_seconds == 45
        assert monitor.expected_status == 201
        assert monitor.is_public is False

    deleted = admin_client.post(f"/monitors/{monitor_id}/delete", follow_redirects=True)
    assert deleted.status_code == 200
    with app.app_context():
        assert Monitor.query.get(monitor_id) is None


def db_monitor(monitor_id):
    from models import Monitor

    return Monitor.query.get(monitor_id)


def test_enable_disable(admin_client, app):
    with app.app_context():
        monitor = make_monitor(name="Toggle Me")
        monitor_id = monitor.id
        assert monitor.is_enabled is True

    admin_client.post(f"/monitors/{monitor_id}/toggle")
    with app.app_context():
        assert Monitor.query.get(monitor_id).is_enabled is False

    admin_client.post(f"/monitors/{monitor_id}/toggle")
    with app.app_context():
        assert Monitor.query.get(monitor_id).is_enabled is True


def test_duplicate_monitor_rejected(admin_client, app):
    with app.app_context():
        make_monitor(name="Unique", url="https://example.com/one")

    response = admin_client.post(
        "/monitors",
        data={
            "name": "Unique",
            "url": "https://example.com/one",
            "interval_seconds": "30",
            "timeout_seconds": "5",
            "expected_status": "200",
            "visibility": "private",
        },
        follow_redirects=True,
    )
    assert b"already exists" in response.data


def test_ssrf_blocked_on_create(admin_client):
    response = admin_client.post(
        "/monitors",
        data={
            "name": "Internal",
            "url": "http://127.0.0.1/secret",
            "interval_seconds": "30",
            "timeout_seconds": "5",
            "expected_status": "200",
            "visibility": "private",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"blocked" in response.data.lower() or b"cannot be monitored" in response.data.lower() or b"private" in response.data.lower()


def test_successful_and_failed_health_check(app):
    with app.app_context():
        monitor = make_monitor(name="API")
        ok, _ = record_check(
            monitor,
            CheckResult(True, http_status=200, response_ms=120),
        )
        assert ok.is_up is True
        assert monitor.last_status == "UP"
        assert monitor.last_http_status == 200
        assert monitor.uptime_percent == 100

        record_check(
            monitor,
            CheckResult(
                False,
                http_status=500,
                response_ms=80,
                error_type="unexpected_status",
                error_message="Expected HTTP 200 but received HTTP 500.",
            ),
        )
        assert monitor.last_status == "DOWN"
        assert monitor.check_count == 2
        assert monitor.success_count == 1


def test_incident_create_no_duplicate_and_recovery(app):
    with app.app_context():
        monitor = make_monitor(name="Payments")
        record_check(
            monitor,
            CheckResult(True, http_status=200, response_ms=90),
        )
        record_check(
            monitor,
            CheckResult(False, http_status=503, error_type="unexpected_status", error_message="HTTP 503"),
        )
        record_check(
            monitor,
            CheckResult(False, http_status=503, error_type="unexpected_status", error_message="HTTP 503"),
        )
        incidents = Incident.query.filter_by(monitor_id=monitor.id).all()
        assert len(incidents) == 1
        assert incidents[0].status == "active"

        record_check(
            monitor,
            CheckResult(True, http_status=200, response_ms=100),
        )
        incident = Incident.query.filter_by(monitor_id=monitor.id).one()
        assert incident.status == "recovered"
        assert incident.recovered_at is not None
        assert incident.duration_seconds >= 0


def test_recommendations(app):
    from extensions import db
    from models import MonitorCheck

    with app.app_context():
        monitor = make_monitor(name="Website")
        record_check(
            monitor,
            CheckResult(
                False,
                http_status=500,
                error_type="unexpected_status",
                error_message="Expected HTTP 200 but received HTTP 500.",
            ),
        )
        recs = Recommendation.query.filter_by(monitor_id=monitor.id).all()
        assert any("500" in r.message or "500" in r.title for r in recs)

        monitor2 = make_monitor(name="Slow", url="https://example.com/slow")
        for _ in range(3):
            db.session.add(
                MonitorCheck(
                    monitor_id=monitor2.id,
                    is_up=True,
                    http_status=200,
                    response_ms=900,
                )
            )
            monitor2.check_count += 1
            monitor2.success_count += 1
        latest = MonitorCheck(
            monitor_id=monitor2.id,
            is_up=True,
            http_status=200,
            response_ms=950,
        )
        db.session.add(latest)
        db.session.flush()
        generate_recommendations(monitor2, latest)
        db.session.commit()
        assert Recommendation.query.filter_by(category="high_latency").count() >= 1

        timeout_monitor = make_monitor(name="Timeouts", url="https://example.com/t")
        record_check(
            timeout_monitor,
            CheckResult(False, error_type="timeout", error_message="timeout"),
        )
        assert Recommendation.query.filter_by(category="timeout").count() >= 1
        recovered = make_monitor(name="Recovered", url="https://example.com/r")
        record_check(recovered, CheckResult(False, http_status=500, error_type="unexpected_status", error_message="down"))
        record_check(recovered, CheckResult(True, http_status=200, response_ms=40))
        assert Recommendation.query.filter_by(category="recovery").count() >= 1
