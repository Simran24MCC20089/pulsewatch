from flask import Blueprint, current_app, jsonify

from models import Monitor
from services.status import compute_overall_status, public_service_payload

api_bp = Blueprint("api", __name__)


@api_bp.route("/api/public/status")
def public_status_api():
    high_latency = current_app.config.get("HIGH_LATENCY_MS", 800)
    monitors = (
        Monitor.query.filter_by(is_public=True, is_enabled=True)
        .order_by(Monitor.name.asc())
        .all()
    )
    overall = compute_overall_status(monitors, high_latency)
    services = []
    for monitor in monitors:
        item = public_service_payload(monitor, high_latency)
        services.append(
            {
                "name": item["name"],
                "status": item["status"],
                "response_time": item["response_time"],
                "uptime": item["uptime"],
                "last_checked": item["last_checked"],
            }
        )
    return jsonify({"overall_status": overall, "services": services})
