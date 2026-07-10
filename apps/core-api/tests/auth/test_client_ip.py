from __future__ import annotations

from inkforge_core.auth.client_ip import resolve_client_identity
from starlette.requests import Request


def make_request(peer: str, x_real_ip: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if x_real_ip is not None:
        headers.append((b"x-real-ip", x_real_ip.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": headers,
            "client": (peer, 12345),
        }
    )


def make_request_with_forwarded_values(peer: str, values: list[str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [(b"x-real-ip", value.encode("ascii")) for value in values],
            "client": (peer, 12345),
        }
    )


def test_untrusted_peer_cannot_spoof_x_real_ip() -> None:
    request = make_request("203.0.113.10", "198.51.100.20")
    assert resolve_client_identity(request, ("172.16.0.0/12",)) == "203.0.113.10"


def test_trusted_proxy_can_forward_one_strict_ip() -> None:
    request = make_request("172.18.0.2", "198.51.100.20")
    assert resolve_client_identity(request, ("172.16.0.0/12",)) == "198.51.100.20"


def test_trusted_proxy_ignores_invalid_or_multiple_forwarded_values() -> None:
    invalid = make_request("172.18.0.2", "not-an-ip")
    multiple = make_request("172.18.0.2", "198.51.100.20, 10.0.0.1")

    assert resolve_client_identity(invalid, ("172.16.0.0/12",)) == "172.18.0.2"
    assert resolve_client_identity(multiple, ("172.16.0.0/12",)) == "172.18.0.2"


def test_trusted_proxy_ignores_duplicate_x_real_ip_headers() -> None:
    request = make_request_with_forwarded_values(
        "172.18.0.2", ["198.51.100.20", "198.51.100.21"]
    )
    assert resolve_client_identity(request, ("172.16.0.0/12",)) == "172.18.0.2"


def test_ipv6_peer_and_forwarded_address_are_normalized() -> None:
    request = make_request("2001:db8::2", "2001:db8:0:1::9")
    assert resolve_client_identity(request, ("2001:db8::/32",)) == "2001:db8:0:1::9"
