"""快盒报销附件场景；权限随所属报销单，不随人员任职公司。"""
from app.modules.file.service import register_file_access, register_file_scene
from . import access_repository
from .models import SampleReimbursement

SCENE = "sample_app_invoice"
BUSINESS_TYPE = "sample_app_reimbursement"

# 不继承 document 的 Office 类型白名单，只允许发票 PDF 和图片。
register_file_scene(SCENE, kinds={"image"}, max_bytes=20 * 1024 * 1024,
                    max_count=50, extra_content_types={"application/pdf": "pdf"})


async def can_read(session, user, business_id):
    if "sample_app" not in user.enabled_plugin_keys:
        return False
    if "sample_app:access" in user.permissions:
        if await access_repository.record_org(session, user, SampleReimbursement, business_id) is not None:
            return True
    from .employee_mcp_service import can_read_own_reimbursement
    return await can_read_own_reimbursement(session, user, business_id)


register_file_access(BUSINESS_TYPE, can_read)
