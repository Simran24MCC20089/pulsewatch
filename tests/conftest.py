import os
import socket

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from config import TestConfig
from extensions import db
from models import Monitor


TEST_PASSWORD = "secret"
TEST_USER = "admin"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("PULSEWATCH_USERNAME", TEST_USER)
    monkeypatch.setenv(
        "PULSEWATCH_PASSWORD_HASH",
        generate_password_hash(TEST_PASSWORD, method="pbkdf2:sha256"),
    )
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")

    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("services.ssrf.socket.getaddrinfo", fake_getaddrinfo)

    class DummyRaw:
        def read(self, n):
            return b"ok"

    class DummyResponse:
        status_code = 200
        is_redirect = False
        headers = {}
        raw = DummyRaw()

        def close(self):
            return None

    monkeypatch.setattr("services.checker.requests.get", lambda *a, **k: DummyResponse())

    application = create_app(TestConfig)
    application.config["PULSEWATCH_USERNAME"] = TEST_USER
    application.config["PULSEWATCH_PASSWORD_HASH"] = os.environ["PULSEWATCH_PASSWORD_HASH"]
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_client(client):
    client.post(
        "/login",
        data={"username": TEST_USER, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    return client


def make_monitor(**kwargs):
    values = {
        "name": kwargs.pop("name", "Website"),
        "url": kwargs.pop("url", "https://example.com/health"),
        "interval_seconds": kwargs.pop("interval_seconds", 30),
        "timeout_seconds": kwargs.pop("timeout_seconds", 5),
        "expected_status": kwargs.pop("expected_status", 200),
        "is_public": kwargs.pop("is_public", True),
        "is_enabled": kwargs.pop("is_enabled", True),
    }
    values.update(kwargs)
    monitor = Monitor(**values)
    db.session.add(monitor)
    db.session.commit()
    return monitor
