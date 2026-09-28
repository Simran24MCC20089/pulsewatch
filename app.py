import os

from flask import Flask

from config import Config
from extensions import db
from models import Incident, Monitor, MonitorCheck, Recommendation  # noqa: F401
from routes.admin import admin_bp
from routes.api import api_bp
from routes.auth import auth_bp
from routes.public import public_bp
from services.scheduler import start_scheduler


def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or Config)
    app.config["PULSEWATCH_USERNAME"] = os.environ.get(
        "PULSEWATCH_USERNAME", app.config.get("PULSEWATCH_USERNAME", "")
    )
    app.config["PULSEWATCH_PASSWORD_HASH"] = os.environ.get(
        "PULSEWATCH_PASSWORD_HASH", app.config.get("PULSEWATCH_PASSWORD_HASH", "")
    )
    if os.environ.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
    if os.environ.get("DATABASE_URL") and not app.config.get("TESTING"):
        app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    with app.app_context():
        db.create_all()

    if not app.config.get("TESTING"):
        start_scheduler(app)

    @app.context_processor
    def inject_globals():
        from flask import session

        active = 0
        if session.get("admin_authenticated"):
            try:
                active = Incident.query.filter_by(status="active").count()
            except Exception:
                active = 0
        return {
            "app_name": app.config.get("APP_NAME", "PulseWatch"),
            "app_version": app.config.get("APP_VERSION", "1.0.0"),
            "environment": app.config.get("ENVIRONMENT", "development"),
            "metrics": {"active_incidents": active},
        }

    @app.errorhandler(404)
    def not_found(_e):
        return (
            "<!doctype html><title>Not found</title><h1>Not found</h1>",
            404,
        )

    return app


if __name__ == "__main__":
    application = create_app()
    port = int(os.environ.get("PORT", "5000"))
    debug = application.config.get("ENVIRONMENT") != "production"
    application.run(host="0.0.0.0", port=port, debug=debug, use_reloader=debug)
