from __future__ import annotations

import logging
from datetime import timedelta

from extensions import db, scheduler
from models import Monitor, utcnow
from services.checker import run_monitor_check

logger = logging.getLogger(__name__)


def _due_monitors():
    now = utcnow()
    monitors = Monitor.query.filter_by(is_enabled=True).all()
    due = []
    for monitor in monitors:
        if monitor.last_checked_at is None:
            due.append(monitor)
            continue
        last = monitor.last_checked_at
        if last.tzinfo is None:
            from datetime import timezone

            last = last.replace(tzinfo=timezone.utc)
        if last + timedelta(seconds=monitor.interval_seconds) <= now:
            due.append(monitor)
    return due


def tick(app):
    with app.app_context():
        try:
            due = _due_monitors()
            for monitor in due:
                try:
                    run_monitor_check(monitor)
                except Exception:  # noqa: BLE001
                    logger.exception("Monitor check failed for %s", monitor.id)
                    db.session.rollback()
        except Exception:
            logger.exception("Scheduler tick failed")
            db.session.rollback()


def start_scheduler(app):
    if app.config.get("TESTING"):
        return
    if scheduler.running:
        return

    interval = int(app.config.get("SCHEDULER_TICK_SECONDS", 5) or 5)
    if interval <= 0:
        return

    scheduler.add_job(
        func=tick,
        args=[app],
        trigger="interval",
        seconds=interval,
        id="pulsewatch-monitor-tick",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("PulseWatch monitoring engine started (tick=%ss)", interval)
