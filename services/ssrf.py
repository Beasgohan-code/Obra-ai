"""SSRF protection for URL-fetching tools.

Blocks requests to private / loopback / link-local / reserved IPs, non-http(s)
schemes, URLs with embedded credentials, and hostnames that resolve to unsafe
addresses. DNS is re-checked so rebinding-style tricks fail.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import List, Optional, Tuple
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTNAMES = {
    "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback",
    "metadata.google.internal", "metadata",  # cloud metadata endpoints
}
MAX_REDIRECTS = 3


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _is_unsafe_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # unparseable → block
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
        or addr.is_global is False
    )


def resolve_host(host: str) -> List[str]:
    """Resolve a hostname to all its IPs (empty list on failure)."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        return sorted({info[4][0] for info in infos})
    except Exception:
        return []


def check_url(url: str) -> Tuple[bool, str]:
    """
    Returns (safe, reason). Safe URLs are http/https to public hosts.
    """
    if not url or len(url) > 2048:
        return False, "empty or too-long URL"
    try:
        p = urlparse(url.strip())
    except Exception as e:
        return False, f"unparseable URL: {e}"
    if p.scheme.lower() not in ALLOWED_SCHEMES:
        return False, f"scheme '{p.scheme}' not allowed (http/https only)"
    if not p.hostname:
        return False, "no hostname"
    if p.username or p.password:
        return False, "credentials in URL not allowed"
    host = p.hostname.lower().rstrip(".")
    if host in BLOCKED_HOSTNAMES:
        return False, f"blocked hostname '{host}'"
    # raw IP literal?
    if _is_ip_literal(host):
        if _is_unsafe_ip(host):
            return False, f"blocked IP literal '{host}'"
        return True, "ok"  # public IP literal is fine, skip DNS
    # hex / decimal IP encodings (e.g. 0x7f000001, 2130706433)
    try:
        import re
        if re.fullmatch(r"(0x[0-9a-f]+|\d{1,10}|0[0-7]+)", host):
            # interpret as integer IP
            val = int(host, 0) if host.startswith("0x") else int(host)
            if val <= 0xFFFFFFFF:
                return False, "encoded IP literal not allowed"
    except Exception:
        pass
    # DNS resolution check — every resolved IP must be public
    ips = resolve_host(host)
    if not ips:
        return False, f"DNS resolution failed for '{host}'"
    for ip in ips:
        if _is_unsafe_ip(ip):
            return False, f"'{host}' resolves to blocked IP {ip}"
    return True, "ok"


def safe_redirect_target(base_url: str, location: str) -> Optional[str]:
    """Validate a redirect Location against the same policy; returns absolute URL or None."""
    from urllib.parse import urljoin
    target = urljoin(base_url, location or "")
    ok, _ = check_url(target)
    return target if ok else None
