from __future__ import annotations

from datetime import datetime, timezone

from models import Incident, utcnow
from extensions import db


def apply_incident_transition(monitor, is_up: bool, http_status, error_type, error_message) -> Incident | None:
    """Create or recover incidents based on UP/DOWN transitions.

    Returns the incident that was created or recovered, if any.
    """
    open_incident = (
        Incident.query.filter_by(monitor_id=monitor.id, status="active")
        .order_by(Incident.started_at.desc())
        .first()
    )

    if not is_up:
        if open_incident:
            return None
        incident = Incident(
            monitor_id=monitor.id,
            status="active",
            started_at=utcnow(),
            http_status=http_status,
            error_type=error_type,
            error_message=(error_message or "")[:500],
            description=(
                f"{monitor.name} is down. "
                f"{error_message or f'HTTP {http_status}' if http_status else 'Health check failed.'}"
            )[:500],
        )
        db.session.add(incident)
        db.session.flush()
        return incident

    if open_incident:
        open_incident.status = "recovered"
        open_incident.recovered_at = utcnow()
        return open_incident

    return None
