"""供应商短时读取受控参考图；旧 Render/Take 公共资源已退场。"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from ...errors import ApiError
from ..provider_asset import VideoProviderAssetService

router = APIRouter(prefix="/video", tags=["逐镜视频生成"])


def get_video_provider_asset_service(request: Request) -> VideoProviderAssetService:
    service = cast(
        VideoProviderAssetService | None,
        getattr(request.app.state, "video_provider_asset_service", None),
    )
    if service is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_PROVIDER_ASSET_TRANSPORT_DISABLED",
            message="供应商素材传输未启用",
        )
    return service


Service = Annotated[VideoProviderAssetService, Depends(get_video_provider_asset_service)]


@router.get(
    "/provider-assets/{token}",
    response_class=FileResponse,
    include_in_schema=False,
)
async def get_provider_asset(token: str, service: Service) -> FileResponse:
    """只凭短时 HMAC token 返回已确认参考图；该地址供 Seedance 拉取。"""

    path, mime_type = await service.get_file(token)
    return FileResponse(path, media_type=mime_type)
