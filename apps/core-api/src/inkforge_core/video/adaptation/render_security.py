"""供应商参考图短时令牌与结果 URL 出网护栏。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from urllib.parse import urlsplit

from ...errors import ApiError


@dataclass(frozen=True, slots=True)
class ProviderAssetGrant:
    asset_id: str
    sha256: str
    expires_at: datetime


class ProviderAssetTokenCodec:
    """生成不依赖数据库 session 的短时 HMAC 素材地址。"""

    def __init__(self, secret: str, *, lifetime: timedelta = timedelta(minutes=10)) -> None:
        if len(secret.encode()) < 32 or lifetime <= timedelta(0):
            raise ValueError("供应商素材令牌配置无效")
        self._secret = secret.encode()
        self._lifetime = lifetime

    def encode(self, *, asset_id: str, sha256: str, now: datetime | None = None) -> str:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        payload = json.dumps(
            {
                "assetId": asset_id,
                "sha256": sha256,
                "exp": int((current + self._lifetime).timestamp()),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        encoded = _base64url(payload)
        signature = _base64url(hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest())
        return f"{encoded}.{signature}"

    def decode(self, token: str, *, now: datetime | None = None) -> ProviderAssetGrant:
        try:
            encoded, signature = token.split(".", 1)
            expected = _base64url(
                hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(signature, expected):
                raise ValueError("签名不匹配")
            payload = json.loads(_base64url_decode(encoded))
            asset_id = payload["assetId"]
            sha256 = payload["sha256"]
            expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
            if not isinstance(asset_id, str) or not isinstance(sha256, str):
                raise ValueError("字段类型无效")
            if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
                raise ValueError("哈希无效")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ApiError(
                status_code=404,
                code="VIDEO_PROVIDER_ASSET_TOKEN_INVALID",
                message="供应商素材地址无效或已过期",
            ) from exc
        current = (now or datetime.now(UTC)).astimezone(UTC)
        if expires_at <= current:
            raise ApiError(
                status_code=404,
                code="VIDEO_PROVIDER_ASSET_TOKEN_EXPIRED",
                message="供应商素材地址已过期",
            )
        return ProviderAssetGrant(asset_id=asset_id, sha256=sha256, expires_at=expires_at)


def require_allowed_seedance_result_url(url: str, suffixes: tuple[str, ...]) -> str:
    """只接受配置内的公网 HTTPS 域名；拒绝凭 URL 访问任意内网。"""

    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise ValueError("SEEDANCE_RESULT_URL_INVALID")
    try:
        ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("SEEDANCE_RESULT_URL_IP_FORBIDDEN")
    if not any(host.endswith(suffix) and host != suffix.removeprefix(".") for suffix in suffixes):
        raise ValueError("SEEDANCE_RESULT_HOST_FORBIDDEN")
    return url


def _base64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _base64url_decode(payload: str) -> bytes:
    return base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
