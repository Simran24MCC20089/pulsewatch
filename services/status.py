from __future__ import annotations

from models import Incident, Monitor


DOWN = "DOWN"
DEGRADED = "DEGRADED"
OPERATIONAL = "operational"
OPERATIONAL_LABEL = "OPERATIONAL"


def public_monitors_query():
    return Monitor.query.filter_by(is_public=True, is_enabled=True)


def client_status_message(overall: str) -> str:
    if overall == "down":
        return "One or more public services are currently unavailable."
    if overall == "degraded":
        return "Some requests are currently experiencing increased response times."
    return "All public services are operating normally."


def compute_overall_status(monitors: list[Monitor], high_latency_ms: int = 800) -> str:
    """Derive overall public status from live monitor rows.

    Rules:
    - down: at least one public enabled service is DOWN
    - degraded: all remaining services are UP, but at least one is slow or unknown
    - operational: every public enabled service is UP and not slow
    - operational (empty): no public services configured
    """
    if not monitors:
        return "operational"

    if any(m.last_status == DOWN for m in monitors):
        return "down"

    for monitor in monitors:
        if monitor.last_status in ("UNKNOWN", None, ""):
            return "degraded"
        if monitor.last_response_ms is not None and monitor.last_response_ms >= high_latency_ms:
            return "degraded"
        if monitor.last_status != "UP":
            return "degraded"

    return "operational"


def overall_label(status: str) -> str:
    return {
        "operational": "All Systems Operational",
        "degraded": "Degraded Performance",
        "down": "Service Disruption",
    }.get(status, "All Systems Operational")


def public_service_payload(monitor: Monitor, high_latency_ms: int = 800) -> dict:
    status = monitor.last_status or "UNKNOWN"
    display = "Operational"
    if status == "DOWN":
        display = "Unavailable"
    elif status == "UNKNOWN":
        display = "Pending"
    elif monitor.last_response_ms is not None and monitor.last_response_ms >= high_latency_ms:
        display = "Degraded"
        status = "DEGRADED"

    active = (
        Incident.query.filter_by(monitor_id=monitor.id, status="active").first()
        if status == "DOWN"
        else None
    )
    return {
        "id": monitor.id,
        "name": monitor.name,
        "status": "UP" if monitor.last_status == "UP" and display != "Degraded" else (
            "DOWN" if monitor.last_status == "DOWN" else display.upper() if display == "Pending" else (
                "DEGRADED" if display == "Degraded" else monitor.last_status
            )
        ),
        "display_status": display,
        "response_time": monitor.last_response_ms,
        "uptime": monitor.uptime_percent,
        "last_checked": monitor.last_checked_at.isoformat() if monitor.last_checked_at else None,
        "http_status": monitor.last_http_status,
        "incident": (
            {
                "started_at": active.started_at.isoformat() if active else None,
                "description": "This service is currently unavailable.",
            }
            if active
            else None
        ),
    }
