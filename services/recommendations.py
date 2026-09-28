from __future__ import annotations

from models import Monitor, MonitorCheck, Recommendation
from extensions import db


HIGH_LATENCY_STREAK = 3
LOW_UPTIME_THRESHOLD = 95.0


def _add_recommendation(monitor, category, title, message, incident_id=None) -> Recommendation:
    rec = Recommendation(
        monitor_id=monitor.id if monitor else None,
        incident_id=incident_id,
        category=category,
        title=title,
        message=message,
        is_admin_only=True,
    )
    db.session.add(rec)
    return rec


def generate_recommendations(monitor: Monitor, check: MonitorCheck, incident=None) -> list[Recommendation]:
    """Analyze a check result and persist admin diagnostic recommendations."""
    created: list[Recommendation] = []

    if check.error_type == "timeout":
        created.append(
            _add_recommendation(
                monitor,
                "timeout",
                f"{monitor.name}: request timed out",
                "The service did not respond within the configured timeout. "
                "Possible cause: the process is overloaded, unreachable, or blocked by the network. "
                "Recommended check: verify service availability and network connectivity.",
                incident.id if incident else None,
            )
        )
    elif check.error_type == "connection":
        created.append(
            _add_recommendation(
                monitor,
                "connection",
                f"{monitor.name}: connection failed",
                "PulseWatch could not establish a connection. "
                "Possible cause: DNS failure, TLS error, or the host is refusing connections. "
                "Recommended check: confirm the hostname, TLS certificate, and that the service is listening.",
                incident.id if incident else None,
            )
        )
    elif check.http_status == 500:
        created.append(
            _add_recommendation(
                monitor,
                "http_500",
                f"{monitor.name}: HTTP 500",
                "Server returned HTTP 500. "
                "Possible cause: an unhandled application error. "
                "Recommended check: review application logs and recent deployments.",
                incident.id if incident else None,
            )
        )
    elif check.http_status == 404:
        created.append(
            _add_recommendation(
                monitor,
                "http_404",
                f"{monitor.name}: HTTP 404",
                "The configured endpoint returned 404. "
                "Possible cause: the path was moved or mistyped. "
                "Recommended check: verify the URL and API route.",
                incident.id if incident else None,
            )
        )
    elif check.http_status is not None and check.http_status >= 500:
        created.append(
            _add_recommendation(
                monitor,
                "http_5xx",
                f"{monitor.name}: HTTP {check.http_status}",
                f"The service returned HTTP {check.http_status}. "
                "Possible cause: an upstream or application failure. "
                "Recommended check: review application logs, dependencies, and recent changes.",
                incident.id if incident else None,
            )
        )
    elif check.http_status is not None and check.http_status >= 400:
        created.append(
            _add_recommendation(
                monitor,
                "http_4xx",
                f"{monitor.name}: HTTP {check.http_status}",
                f"The service returned HTTP {check.http_status}. "
                "Possible cause: authentication, routing, or request mismatch. "
                "Suggested action: confirm the expected status code and the public URL.",
                incident.id if incident else None,
            )
        )

    if (
        check.is_up
        and check.response_ms is not None
        and check.response_ms >= 800
    ):
        recent = (
            MonitorCheck.query.filter_by(monitor_id=monitor.id)
            .order_by(MonitorCheck.checked_at.desc())
            .limit(HIGH_LATENCY_STREAK)
            .all()
        )
        if len(recent) >= HIGH_LATENCY_STREAK and all(
            c.response_ms is not None and c.response_ms >= 800 for c in recent
        ):
            created.append(
                _add_recommendation(
                    monitor,
                    "high_latency",
                    f"{monitor.name}: high response time",
                    "Response time is consistently high. "
                    "Possible cause: server load, slow queries, or network latency. "
                    "Recommended check: review server load, database performance and network latency.",
                )
            )

    if monitor.check_count >= 10 and monitor.uptime_percent < LOW_UPTIME_THRESHOLD:
        created.append(
            _add_recommendation(
                monitor,
                "low_uptime",
                f"{monitor.name}: availability decreased",
                "Service availability has decreased. "
                "Possible cause: repeated failures or a prolonged outage. "
                "Recommended check: review recent incidents and deployment changes.",
            )
        )

    if incident is not None and incident.status == "recovered":
        created.append(
            _add_recommendation(
                monitor,
                "recovery",
                f"{monitor.name}: service recovered",
                "Service has recovered. "
                "Recommendation: review the incident timeline if the issue repeats.",
                incident.id,
            )
        )

    return created
