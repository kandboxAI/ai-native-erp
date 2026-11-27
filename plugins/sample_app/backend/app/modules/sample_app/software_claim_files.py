"""软件报销凭证附件场景：微信/支付宝扣款截图或 invoice 原件。"""
from app.modules.file.service import register_file_access, register_file_scene

SCENE = "sample_app_software_claim"
BUSINESS_TYPE = "sample_app_software_claim"

register_file_scene(
    SCENE,
    kinds={"image"},
    max_bytes=20 * 1024 * 1024,
    max_count=20,
    extra_content_types={"application/pdf": "pdf"},
)


async def can_read(session, user, business_id):
    if "sample_app" not in user.enabled_plugin_keys:
        return False
    if "sample_app:access" in user.permissions:
        from . import access_repository
        from .employee_mcp_models import SoftwareClaim
        if await access_repository.record_org(session, user, SoftwareClaim, business_id) is not None:
            return True
    from . import software_claim_service
    return await software_claim_service.can_read_own_claim(session, user, business_id)


register_file_access(BUSINESS_TYPE, can_read)
