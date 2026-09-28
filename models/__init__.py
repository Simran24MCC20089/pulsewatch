from datetime import datetime, timezone

from extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class Monitor(db.Model):
    __tablename__ = "monitors"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    url = db.Column(db.String(2048), unique=True, nullable=False)
    interval_seconds = db.Column(db.Integer, nullable=False, default=60)
    timeout_seconds = db.Column(db.Integer, nullable=False, default=5)
    expected_status = db.Column(db.Integer, nullable=False, default=200)
    is_public = db.Column(db.Boolean, nullable=False, default=False)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    last_status = db.Column(db.String(16), nullable=False, default="UNKNOWN")
    last_http_status = db.Column(db.Integer, nullable=True)
    last_response_ms = db.Column(db.Float, nullable=True)
    last_checked_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.String(500), nullable=True)
    next_check_at = db.Column(db.DateTime, nullable=True)

    check_count = db.Column(db.Integer, nullable=False, default=0)
    success_count = db.Column(db.Integer, nullable=False, default=0)

    checks = db.relationship(
        "MonitorCheck",
        backref="monitor",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="desc(MonitorCheck.checked_at)",
    )
    incidents = db.relationship(
        "Incident",
        backref="monitor",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="desc(Incident.started_at)",
    )
    recommendations = db.relationship(
        "Recommendation",
        backref="monitor",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="desc(Recommendation.created_at)",
    )

    @property
    def uptime_percent(self) -> float:
        if self.check_count == 0:
            return 0.0
        return round((self.success_count / self.check_count) * 100.0, 2)

    @property
    def is_up(self) -> bool:
        return self.last_status == "UP"

    @property
    def is_down(self) -> bool:
        return self.last_status == "DOWN"


class MonitorCheck(db.Model):
    __tablename__ = "monitor_checks"

    id = db.Column(db.Integer, primary_key=True)
    monitor_id = db.Column(db.Integer, db.ForeignKey("monitors.id"), nullable=False, index=True)
    checked_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    is_up = db.Column(db.Boolean, nullable=False)
    http_status = db.Column(db.Integer, nullable=True)
    response_ms = db.Column(db.Float, nullable=True)
    error_type = db.Column(db.String(64), nullable=True)
    error_message = db.Column(db.String(500), nullable=True)


class Incident(db.Model):
    __tablename__ = "incidents"

    id = db.Column(db.Integer, primary_key=True)
    monitor_id = db.Column(db.Integer, db.ForeignKey("monitors.id"), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, default="active")
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    recovered_at = db.Column(db.DateTime, nullable=True)
    http_status = db.Column(db.Integer, nullable=True)
    error_type = db.Column(db.String(64), nullable=True)
    error_message = db.Column(db.String(500), nullable=True)
    description = db.Column(db.String(500), nullable=False, default="")

    @property
    def duration_seconds(self) -> float:
        end = self.recovered_at or utcnow()
        start = self.started_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return max(0.0, (end - start).total_seconds())

    def duration_label(self) -> str:
        seconds = int(self.duration_seconds)
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        if hours:
            return f"{hours}h {minutes}m {secs}s"
        if minutes:
            return f"{minutes}m {secs}s"
        return f"{secs}s"


class Recommendation(db.Model):
    __tablename__ = "recommendations"

    id = db.Column(db.Integer, primary_key=True)
    monitor_id = db.Column(db.Integer, db.ForeignKey("monitors.id"), nullable=True, index=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("incidents.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    category = db.Column(db.String(64), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.String(800), nullable=False)
    is_admin_only = db.Column(db.Boolean, nullable=False, default=True)
