from __future__ import annotations

import time
from urllib.parse import urljoin

import requests
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import SSLError, Timeout, TooManyRedirects

from extensions import db
from models import Monitor, MonitorCheck, utcnow
from services.incidents import apply_incident_transition
from services.recommendations import generate_recommendations
from services.ssrf import UnsafeURLError, validate_public_http_url

USER_AGENT = "PulseWatch/1.0 (+https://pulsewatch.local; health-check)"
MAX_REDIRECTS = 5
MAX_BODY = 64 * 1024


class CheckResult:
    def __init__(
        self,
        is_up: bool,
        http_status=None,
        response_ms=None,
        error_type=None,
        error_message=None,
    ):
        self.is_up = is_up
        self.http_status = http_status
        self.response_ms = response_ms
        self.error_type = error_type
        self.error_message = error_message


def _safe_get(url: str, timeout: float) -> requests.Response:
    current = url
    last_response = None
    for _ in range(MAX_REDIRECTS + 1):
        validate_public_http_url(current, resolve=True)
        start = time.perf_counter()
        response = requests.get(
            current,
            timeout=timeout,
            allow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            stream=True,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        response.elapsed_ms = elapsed_ms  # type: ignore[attr-defined]
        try:
            response.raw.read(MAX_BODY)
        except Exception:
            pass
        response.close()
        last_response = response
        if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            if not location:
                return response
            current = urljoin(current, location)
            continue
        return response
    raise TooManyRedirects("Exceeded redirect limit")


def execute_http_check(url: str, timeout_seconds: int, expected_status: int) -> CheckResult:
    try:
        validate_public_http_url(url, resolve=True)
    except UnsafeURLError as exc:
        return CheckResult(
            is_up=False,
            error_type="blocked",
            error_message=str(exc),
        )

    try:
        response = _safe_get(url, timeout=float(timeout_seconds))
        http_status = response.status_code
        response_ms = round(getattr(response, "elapsed_ms", response.elapsed.total_seconds() * 1000), 2)
        is_up = http_status == expected_status
        error_type = None
        error_message = None
        if not is_up:
            error_type = "unexpected_status"
            error_message = (
                f"Expected HTTP {expected_status} but received HTTP {http_status}."
            )
        return CheckResult(
            is_up=is_up,
            http_status=http_status,
            response_ms=response_ms,
            error_type=error_type,
            error_message=error_message,
        )
    except Timeout:
        return CheckResult(
            is_up=False,
            error_type="timeout",
            error_message="The service did not respond within the configured timeout.",
        )
    except SSLError as exc:
        return CheckResult(
            is_up=False,
            error_type="connection",
            error_message=f"TLS/SSL error: {exc}",
        )
    except (RequestsConnectionError, TooManyRedirects, OSError) as exc:
        return CheckResult(
            is_up=False,
            error_type="connection",
            error_message=str(exc)[:500],
        )
    except UnsafeURLError as exc:
        return CheckResult(
            is_up=False,
            error_type="blocked",
            error_message=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 — monitoring must never crash the app
        return CheckResult(
            is_up=False,
            error_type="unknown",
            error_message=str(exc)[:500],
        )


def record_check(monitor: Monitor, result: CheckResult):
    check = MonitorCheck(
        monitor_id=monitor.id,
        checked_at=utcnow(),
        is_up=result.is_up,
        http_status=result.http_status,
        response_ms=result.response_ms,
        error_type=result.error_type,
        error_message=(result.error_message or "")[:500] if result.error_message else None,
    )
    db.session.add(check)

    monitor.check_count = (monitor.check_count or 0) + 1
    if result.is_up:
        monitor.success_count = (monitor.success_count or 0) + 1
    monitor.last_status = "UP" if result.is_up else "DOWN"
    monitor.last_http_status = result.http_status
    monitor.last_response_ms = result.response_ms
    monitor.last_checked_at = check.checked_at
    monitor.last_error = check.error_message
    monitor.next_check_at = utcnow()

    incident = apply_incident_transition(
        monitor,
        is_up=result.is_up,
        http_status=result.http_status,
        error_type=result.error_type,
        error_message=result.error_message,
    )

    generate_recommendations(monitor, check, incident)
    db.session.commit()
    db.session.refresh(monitor)
    return check, incident


def run_monitor_check(monitor: Monitor):
    result = execute_http_check(
        monitor.url, monitor.timeout_seconds, monitor.expected_status
    )
    return record_check(monitor, result)
