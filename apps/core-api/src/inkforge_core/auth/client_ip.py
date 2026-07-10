from __future__ import annotations

from ipaddress import ip_address, ip_network

from starlette.requests import Request


def resolve_client_identity(request: Request, trusted_proxy_cidrs: tuple[str, ...]) -> str:
    """只接受可信直接对端转发的单个真实客户端地址。"""

    if request.client is None:
        return "unknown"
    peer_text = request.client.host
    try:
        peer = ip_address(peer_text)
    except ValueError:
        return peer_text

    trusted_peer = any(
        peer in ip_network(cidr, strict=False) for cidr in trusted_proxy_cidrs
    )
    if not trusted_peer:
        return peer.compressed

    forwarded_values = request.headers.getlist("X-Real-IP")
    if len(forwarded_values) != 1:
        return peer.compressed
    forwarded_text = forwarded_values[0]
    if "," in forwarded_text:
        return peer.compressed
    try:
        forwarded = ip_address(forwarded_text.strip())
    except ValueError:
        return peer.compressed
    return forwarded.compressed
