"""SSRF-safe URL validation for outbound health checks."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
    "metadata.goog",
    "metadata",
    "instance-data",
}


BLOCKED_NETWORKS = [
    ipaddress.ip_network("169.254.169.254/32"),
    ipaddress.ip_network("fd00:ec2::254/128"),
]


# DNS64/NAT64 well-known prefix.
# Addresses in this range contain an IPv4 address in their last 32 bits.
NAT64_NETWORK = ipaddress.ip_network("64:ff9b::/96")


class UnsafeURLError(ValueError):
    """Raised when a URL is not a safe public HTTP(S) destination."""


def _host_to_ip(host: str) -> ipaddress._BaseAddress | None:
    host = host.strip("[]")

    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass

    if host.isdigit():
        try:
            return ipaddress.IPv4Address(int(host))
        except (ValueError, OverflowError):
            return None

    return None


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    """
    Return True when an IP address is unsafe for outbound monitoring.

    Public IPv4/IPv6 addresses are allowed.

    Private, loopback, link-local, multicast, reserved,
    unspecified and cloud metadata addresses are blocked.

    DNS64/NAT64 addresses are handled by extracting their
    embedded IPv4 address and validating that IPv4 address.
    """

    # ---------------------------------------------------------
    # IPv4-mapped IPv6
    # Example:
    # ::ffff:127.0.0.1
    # ---------------------------------------------------------
    if ip.version == 6 and ip.ipv4_mapped:
        return _is_blocked_ip(ip.ipv4_mapped)

    # ---------------------------------------------------------
    # DNS64 / NAT64
    #
    # Example:
    # 64:ff9b::2cdd:d0c0
    #
    # The final 32 bits represent an IPv4 address.
    # ---------------------------------------------------------
    if ip.version == 6 and ip in NAT64_NETWORK:
        embedded_ipv4 = ipaddress.IPv4Address(
            int(ip) & 0xFFFFFFFF
        )

        return _is_blocked_ip(embedded_ipv4)

    # ---------------------------------------------------------
    # Private addresses
    #
    # IPv4:
    # 10.x.x.x
    # 172.16.x.x - 172.31.x.x
    # 192.168.x.x
    #
    # IPv6 private/unique-local:
    # fc00::/7
    # ---------------------------------------------------------
    if ip.is_private:
        return True

    # ---------------------------------------------------------
    # Loopback
    #
    # 127.0.0.0/8
    # ::1
    # ---------------------------------------------------------
    if ip.is_loopback:
        return True

    # ---------------------------------------------------------
    # Link-local
    #
    # 169.254.0.0/16
    # fe80::/10
    # ---------------------------------------------------------
    if ip.is_link_local:
        return True

    # ---------------------------------------------------------
    # Multicast
    # ---------------------------------------------------------
    if ip.is_multicast:
        return True

    # ---------------------------------------------------------
    # Reserved
    # ---------------------------------------------------------
    if ip.is_reserved:
        return True

    # ---------------------------------------------------------
    # Unspecified
    #
    # 0.0.0.0
    # ::
    # ---------------------------------------------------------
    if ip.is_unspecified:
        return True

    # ---------------------------------------------------------
    # IPv6 site-local
    # ---------------------------------------------------------
    if getattr(ip, "is_site_local", False):
        return True

    # ---------------------------------------------------------
    # Explicit cloud metadata addresses
    # ---------------------------------------------------------
    for network in BLOCKED_NETWORKS:
        if ip in network:
            return True

    return False


def _resolve_host(
    hostname: str,
) -> list[ipaddress._BaseAddress]:
    """Resolve a hostname and return all resolved IP addresses."""

    results: list[ipaddress._BaseAddress] = []

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeURLError(
            "The hostname could not be resolved."
        ) from exc

    for info in infos:
        addr = info[4][0]

        try:
            results.append(ipaddress.ip_address(addr))
        except ValueError:
            continue

    if not results:
        raise UnsafeURLError(
            "The hostname could not be resolved to an IP address."
        )

    return results


def validate_public_http_url(
    url: str,
    resolve: bool = True,
) -> str:
    """
    Validate an outbound monitoring URL.

    Only HTTP/HTTPS URLs pointing to safe public destinations
    are allowed.
    """

    if not url or not str(url).strip():
        raise UnsafeURLError("A URL is required.")

    cleaned = str(url).strip()

    parsed = urlparse(cleaned)

    # ---------------------------------------------------------
    # Protocol
    # ---------------------------------------------------------
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(
            "Only public HTTP and HTTPS URLs are allowed."
        )

    # ---------------------------------------------------------
    # Credentials
    #
    # Reject:
    # https://username:password@example.com
    # ---------------------------------------------------------
    if parsed.username or parsed.password:
        raise UnsafeURLError(
            "URLs with embedded credentials are not allowed."
        )

    # ---------------------------------------------------------
    # Hostname
    # ---------------------------------------------------------
    hostname = parsed.hostname

    if not hostname:
        raise UnsafeURLError(
            "The URL must include a hostname."
        )

    host_lower = hostname.lower().rstrip(".")

    # ---------------------------------------------------------
    # Explicitly blocked hostnames
    # ---------------------------------------------------------
    if host_lower in BLOCKED_HOSTNAMES:
        raise UnsafeURLError(
            "That destination is blocked for security reasons."
        )

    # ---------------------------------------------------------
    # Block local/internal hostname suffixes
    # ---------------------------------------------------------
    if host_lower.endswith(".localhost"):
        raise UnsafeURLError(
            "That destination is blocked for security reasons."
        )

    if host_lower.endswith(".local"):
        raise UnsafeURLError(
            "That destination is blocked for security reasons."
        )

    if host_lower.endswith(".internal"):
        raise UnsafeURLError(
            "That destination is blocked for security reasons."
        )

    if host_lower.endswith(".corp"):
        raise UnsafeURLError(
            "That destination is blocked for security reasons."
        )

    # ---------------------------------------------------------
    # If hostname itself is an IP address,
    # validate it directly.
    # ---------------------------------------------------------
    literal_ip = _host_to_ip(host_lower)

    if literal_ip is not None and _is_blocked_ip(literal_ip):
        raise UnsafeURLError(
            "Private, local, and cloud metadata addresses "
            "cannot be monitored."
        )

    # ---------------------------------------------------------
    # Resolve DNS and validate EVERY returned address.
    #
    # This is important for SSRF protection because a hostname
    # must not be allowed to resolve to an internal address.
    # ---------------------------------------------------------
    if resolve:
        resolved_ips = _resolve_host(host_lower)

        for ip in resolved_ips:
            if _is_blocked_ip(ip):
                raise UnsafeURLError(
                    "That URL resolves to a private or internal "
                    "address and cannot be monitored."
                )

    # ---------------------------------------------------------
    # URL length protection
    # ---------------------------------------------------------
    if len(cleaned) > 2048:
        raise UnsafeURLError(
            "URL is too long."
        )

    return cleaned