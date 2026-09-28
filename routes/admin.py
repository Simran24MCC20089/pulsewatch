from __future__ import annotations

from datetime import datetime, timezone

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func, or_

from extensions import db
from models import Incident, Monitor, MonitorCheck, Recommendation
from routes.auth import login_required
from services.checker import run_monitor_check
from services.ssrf import UnsafeURLError, validate_public_http_url

admin_bp = Blueprint("admin", __name__)


def _parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).lower() in ("1", "true", "yes", "on", "public")


def _monitor_filters(query):
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip().upper()
    enabled = (request.args.get("enabled") or "").strip().lower()
    visibility = (request.args.get("visibility") or "").strip().lower()

    if q:
        like = f"%{q}%"
        query = query.filter(or_(Monitor.name.ilike(like), Monitor.url.ilike(like)))
    if status in ("UP", "DOWN", "UNKNOWN"):
        query = query.filter(Monitor.last_status == status)
    if enabled == "enabled":
        query = query.filter(Monitor.is_enabled.is_(True))
    elif enabled == "disabled":
        query = query.filter(Monitor.is_enabled.is_(False))
    if visibility == "public":
        query = query.filter(Monitor.is_public.is_(True))
    elif visibility == "private":
        query = query.filter(Monitor.is_public.is_(False))
    return query, q, status, enabled, visibility


def _form_monitor_fields(form):
    name = (form.get("name") or "").strip()
    url = (form.get("url") or "").strip()
    try:
        interval = int(form.get("interval_seconds") or 60)
    except ValueError:
        interval = -1
    try:
        timeout = int(form.get("timeout_seconds") or 5)
    except ValueError:
        timeout = -1
    try:
        expected = int(form.get("expected_status") or 200)
    except ValueError:
        expected = -1
    is_public = (form.get("visibility") or "private") == "public"
    errors = []
    if not name or len(name) > 120:
        errors.append("Monitor name is required (max 120 characters).")
    if not url:
        errors.append("URL is required.")
    else:
        try:
            url = validate_public_http_url(url, resolve=True)
        except UnsafeURLError as exc:
            errors.append(str(exc))
    if interval < 10 or interval > 3600:
        errors.append("Check interval must be between 10 and 3600 seconds.")
    if timeout < 1 or timeout > 60:
        errors.append("Timeout must be between 1 and 60 seconds.")
    if expected < 100 or expected > 599:
        errors.append("Expected status code must be between 100 and 599.")
    return {
        "name": name,
        "url": url,
        "interval_seconds": interval,
        "timeout_seconds": timeout,
        "expected_status": expected,
        "is_public": is_public,
        "errors": errors,
    }


@admin_bp.route("/dashboard")
@login_required
def dashboard():
    # Dashboard summary metrics
    total = Monitor.query.count()
    online = Monitor.query.filter_by(last_status="UP", is_enabled=True).count()
    active_incidents = Incident.query.filter_by(status="active").count()

    avg_uptime = (
        db.session.query(
            func.avg(
                Monitor.success_count
                * 1.0
                / func.nullif(Monitor.check_count, 0)
                * 100
            )
        )
        .scalar()
    )

    avg_response = (
        db.session.query(func.avg(Monitor.last_response_ms))
        .filter(Monitor.last_response_ms.isnot(None))
        .scalar()
    )

    # Response-time trend: real checks, newest 30, displayed oldest -> newest.
    trend_checks = (
        MonitorCheck.query
        .filter(MonitorCheck.response_ms.isnot(None))
        .order_by(MonitorCheck.checked_at.desc())
        .limit(30)
        .all()
    )
    trend_checks.reverse()

    response_trend = [
        {
            "label": check.checked_at.strftime("%H:%M") if check.checked_at else "",
            "value": round(float(check.response_ms or 0), 1),
        }
        for check in trend_checks
    ]

    # Current service health distribution.
    health_counts = {
        "UP": Monitor.query.filter_by(last_status="UP").count(),
        "DOWN": Monitor.query.filter_by(last_status="DOWN").count(),
        "UNKNOWN": Monitor.query.filter_by(last_status="UNKNOWN").count(),
    }

    # Availability by service, using the real monitor uptime percentage.
    availability = []
    for monitor in Monitor.query.order_by(Monitor.name.asc()).all():
        availability.append(
            {
                "name": monitor.name,
                "uptime": round(float(monitor.uptime_percent or 0), 2),
            }
        )

    # Recent incidents for the compact dashboard view.
    recent_incidents = (
        Incident.query
        .order_by(Incident.started_at.desc())
        .limit(5)
        .all()
    )

    recommendations = (
        Recommendation.query
        .order_by(Recommendation.created_at.desc())
        .limit(6)
        .all()
    )

    return render_template(
        "dashboard.html",
        metrics={
            "monitored": total,
            "online": online,
            "avg_uptime": round(avg_uptime or 0.0, 2),
            "avg_response": round(avg_response or 0.0, 1),
            "active_incidents": active_incidents,
        },
        response_trend=response_trend,
        health_counts=health_counts,
        availability=availability,
        recent_incidents=recent_incidents,
        recommendations=recommendations,
    )


@admin_bp.route("/monitors", methods=["GET", "POST"])
@login_required
def monitors():
    if request.method == "POST":
        data = _form_monitor_fields(request.form)
        if data["errors"]:
            for err in data["errors"]:
                flash(err, "error")
        else:
            exists = Monitor.query.filter(
                or_(Monitor.name == data["name"], Monitor.url == data["url"])
            ).first()
            if exists:
                flash("A monitor with that name or URL already exists.", "error")
            else:
                monitor = Monitor(
                    name=data["name"],
                    url=data["url"],
                    interval_seconds=data["interval_seconds"],
                    timeout_seconds=data["timeout_seconds"],
                    expected_status=data["expected_status"],
                    is_public=data["is_public"],
                    is_enabled=True,
                )
                db.session.add(monitor)
                db.session.commit()
                flash(f"Monitor “{monitor.name}” was added.", "success")
                try:
                    run_monitor_check(monitor)
                    flash("Initial health check completed.", "success")
                except Exception:
                    db.session.rollback()
                    flash("Monitor saved, but the initial check failed.", "error")
                return redirect(url_for("admin.monitors"))

    query = Monitor.query
    query, q, status, enabled, visibility = _monitor_filters(query)
    monitors_list = query.order_by(Monitor.created_at.desc()).all()
    return render_template(
        "monitors.html",
        monitors=monitors_list,
        q=q,
        status=status,
        enabled=enabled,
        visibility=visibility,
    )


@admin_bp.route("/monitors/<int:monitor_id>/edit", methods=["GET", "POST"])
@login_required
def edit_monitor(monitor_id):
    monitor = Monitor.query.get_or_404(monitor_id)
    if request.method == "POST":
        data = _form_monitor_fields(request.form)
        if data["errors"]:
            for err in data["errors"]:
                flash(err, "error")
        else:
            clash = Monitor.query.filter(
                Monitor.id != monitor.id,
                or_(Monitor.name == data["name"], Monitor.url == data["url"]),
            ).first()
            if clash:
                flash("Another monitor already uses that name or URL.", "error")
            else:
                monitor.name = data["name"]
                monitor.url = data["url"]
                monitor.interval_seconds = data["interval_seconds"]
                monitor.timeout_seconds = data["timeout_seconds"]
                monitor.expected_status = data["expected_status"]
                monitor.is_public = data["is_public"]
                db.session.commit()
                flash("Monitor updated.", "success")
                return redirect(url_for("admin.monitors"))
    return render_template("monitor_edit.html", monitor=monitor)


@admin_bp.route("/monitors/<int:monitor_id>/delete", methods=["POST"])
@login_required
def delete_monitor(monitor_id):
    monitor = Monitor.query.get_or_404(monitor_id)
    name = monitor.name
    db.session.delete(monitor)
    db.session.commit()
    flash(f"Monitor “{name}” was deleted.", "success")
    return redirect(url_for("admin.monitors"))


@admin_bp.route("/monitors/<int:monitor_id>/toggle", methods=["POST"])
@login_required
def toggle_monitor(monitor_id):
    monitor = Monitor.query.get_or_404(monitor_id)
    monitor.is_enabled = not monitor.is_enabled
    db.session.commit()
    state = "enabled" if monitor.is_enabled else "disabled"
    flash(f"Monitor “{monitor.name}” is now {state}.", "success")
    return redirect(request.referrer or url_for("admin.monitors"))


@admin_bp.route("/monitors/<int:monitor_id>/check", methods=["POST"])
@login_required
def check_monitor(monitor_id):
    monitor = Monitor.query.get_or_404(monitor_id)
    try:
        check, _incident = run_monitor_check(monitor)
        if check.is_up:
            flash(
                f"{monitor.name} is UP — HTTP {check.http_status} in {check.response_ms} ms.",
                "success",
            )
        else:
            flash(
                f"{monitor.name} is DOWN — {check.error_message or 'health check failed'}.",
                "error",
            )
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        flash(f"Health check could not be completed: {exc}", "error")
    return redirect(request.referrer or url_for("admin.monitors"))


@admin_bp.route("/incidents")
@login_required
def incidents():
    status = (request.args.get("status") or "").strip().lower()
    query = Incident.query
    if status in ("active", "recovered"):
        query = query.filter(Incident.status == status)
    incidents_list = query.order_by(Incident.started_at.desc()).all()
    return render_template("incidents.html", incidents=incidents_list, status=status)


@admin_bp.route("/analytics")
@login_required
def analytics():
    monitors = Monitor.query.order_by(Monitor.name.asc()).all()
    total_checks = db.session.query(func.sum(Monitor.check_count)).scalar() or 0
    total_success = db.session.query(func.sum(Monitor.success_count)).scalar() or 0
    total_failed = total_checks - total_success
    avg_uptime = 0.0
    if total_checks:
        avg_uptime = round((total_success / total_checks) * 100.0, 2)
    avg_response = (
        db.session.query(func.avg(MonitorCheck.response_ms))
        .filter(MonitorCheck.response_ms.isnot(None))
        .scalar()
    )
    incident_count = Incident.query.count()
    active_incidents = Incident.query.filter_by(status="active").count()

    duration_values = []
    for incident in Incident.query.all():
        duration_values.append(incident.duration_seconds)
    avg_incident_duration = round(sum(duration_values) / len(duration_values), 1) if duration_values else 0.0

    trend_monitors = []
    for monitor in monitors:
        points = (
            MonitorCheck.query.filter_by(monitor_id=monitor.id)
            .order_by(MonitorCheck.checked_at.asc())
            .limit(40)
            .all()
        )
        trend_monitors.append(
            {
                "id": monitor.id,
                "name": monitor.name,
                "uptime": monitor.uptime_percent,
                "avg_ms": round(
                    (sum(p.response_ms or 0 for p in points) / len(points)) if points else 0,
                    1,
                ),
                "points": [
                    {
                        "t": p.checked_at.isoformat() if p.checked_at else "",
                        "ms": p.response_ms,
                        "up": p.is_up,
                    }
                    for p in points
                ],
            }
        )

    return render_template(
        "analytics.html",
        monitors=monitors,
        stats={
            "uptime": avg_uptime,
            "avg_response": round(avg_response or 0.0, 1),
            "total_checks": int(total_checks),
            "successful": int(total_success),
            "failed": int(total_failed),
            "incident_count": incident_count,
            "active_incidents": active_incidents,
            "avg_incident_duration": avg_incident_duration,
        },
        trend_monitors=trend_monitors,
    )


@admin_bp.route("/settings")
@login_required
def settings():
    from flask import current_app
    from extensions import scheduler

    engine_status = "running" if scheduler.running else "stopped"
    if current_app.config.get("TESTING"):
        engine_status = "disabled (test mode)"

    return render_template(
        "settings.html",
        username=session.get("admin_username", current_app.config.get("PULSEWATCH_USERNAME")),
        engine_status=engine_status,
        monitor_count=Monitor.query.count(),
        enabled_count=Monitor.query.filter_by(is_enabled=True).count(),
    )
