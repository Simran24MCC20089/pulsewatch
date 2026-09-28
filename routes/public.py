from flask import Blueprint, current_app, jsonify, render_template, abort

from models import Incident, Monitor, MonitorCheck
from services.status import (
    client_status_message,
    compute_overall_status,
    overall_label,
    public_service_payload,
)

public_bp = Blueprint("public", __name__)


@public_bp.route("/")
def landing():
    return render_template("landing.html")


@public_bp.route("/health")
def health():
    return jsonify({"status": "healthy", "service": "PulseWatch"}), 200


@public_bp.route("/status")
def status_page():
    high_latency = current_app.config.get("HIGH_LATENCY_MS", 800)
    monitors = (
        Monitor.query.filter_by(is_public=True, is_enabled=True)
        .order_by(Monitor.name.asc())
        .all()
    )
    overall = compute_overall_status(monitors, high_latency)
    services = [public_service_payload(m, high_latency) for m in monitors]
    return render_template(
        "status.html",
        overall=overall,
        overall_label=overall_label(overall),
        client_message=client_status_message(overall),
        services=services,
    )


@public_bp.route("/status/service/<int:monitor_id>")
def service_status(monitor_id):
    high_latency = current_app.config.get("HIGH_LATENCY_MS", 800)
    monitor = Monitor.query.filter_by(
        id=monitor_id, is_public=True, is_enabled=True
    ).first()
    if not monitor:
        abort(404)

    checks = (
        MonitorCheck.query.filter_by(monitor_id=monitor.id)
        .order_by(MonitorCheck.checked_at.desc())
        .limit(40)
        .all()
    )
    incidents = (
        Incident.query.filter_by(monitor_id=monitor.id)
        .order_by(Incident.started_at.desc())
        .limit(20)
        .all()
    )
    payload = public_service_payload(monitor, high_latency)
    return render_template(
        "service_status.html",
        monitor=monitor,
        service=payload,
        checks=checks,
        incidents=incidents,
        client_message=None,
    )
