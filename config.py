import os

from sqlalchemy.pool import StaticPool

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///pulsewatch.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"check_same_thread": False}}

    PULSEWATCH_USERNAME = os.environ.get("PULSEWATCH_USERNAME", "")
    PULSEWATCH_PASSWORD_HASH = os.environ.get("PULSEWATCH_PASSWORD_HASH", "")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = (
        os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    )
    PERMANENT_SESSION_LIFETIME = 8 * 60 * 60

    APP_NAME = "PulseWatch"
    APP_VERSION = "1.0.0"
    ENVIRONMENT = os.environ.get("PULSEWATCH_ENV", "development")

    HIGH_LATENCY_MS = int(os.environ.get("PULSEWATCH_HIGH_LATENCY_MS", "800"))
    SCHEDULER_TICK_SECONDS = int(os.environ.get("PULSEWATCH_SCHEDULER_TICK", "5"))
    MAX_RESPONSE_BYTES = 64 * 1024


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    SCHEDULER_TICK_SECONDS = 0
    SESSION_COOKIE_SECURE = False
    SECRET_KEY = "test-secret-key"
