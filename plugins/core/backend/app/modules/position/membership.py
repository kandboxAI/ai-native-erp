"""岗位成员由直接账号岗位与已启用插件的有效任职组成，L1 不导入人事模型。"""
from sqlalchemy import exists, or_
from sqlalchemy.orm import aliased
from sqlmodel import select
from app.framework.db.models import utc_now
from app.modules.user_profile.models import SysUser, SysUserPosition
from app.modules.department.models import SysDepartment
from .models import SysPosition
from app.framework.catalog import iter_module_attr
from app.framework.plugin import loaded_plugin_manifests


def position_membership_condition(user, position_id, org_id, *, user_id=None):
    modules = {name for manifest in loaded_plugin_manifests() if manifest.key in user.enabled_plugin_keys
               for name in manifest.module_names}
    conditions = [module.position_membership_condition(user, position_id, org_id, user_id=user_id)
                  for module in iter_module_attr("position_membership", only=modules)]
    subject_id = user.user_id if user_id is None else user_id
    return or_(account_position_membership_condition(subject_id, position_id, org_id), *conditions)



def account_position_membership_condition(user_id, position_id, org_id):
    """直接选岗与雇佣记录独立；停用账号、岗位、部门即撤回资格。"""
    # 批量查看成员时，内层账号使用别名，避免与外层待检查账号混淆。
    account = aliased(SysUser)
    return exists(select(SysUserPosition.id).join(account, account.id == SysUserPosition.user_id)
        .join(SysPosition, SysPosition.id == SysUserPosition.position_id)
        .join(SysDepartment, SysDepartment.id == SysPosition.department_id)
        .where(
            account.id == user_id, account.org_id == org_id, account.is_active.is_(True), account.deleted_at.is_(None),
            SysUserPosition.org_id == org_id, SysUserPosition.deleted_at.is_(None),
            SysUserPosition.valid_from <= utc_now(),
            or_(SysUserPosition.valid_to.is_(None), SysUserPosition.valid_to > utc_now()),
            SysDepartment.org_id == org_id, SysDepartment.is_active.is_(True), SysDepartment.deleted_at.is_(None),
            SysPosition.id == position_id, SysPosition.org_id == org_id, SysPosition.is_active.is_(True), SysPosition.deleted_at.is_(None)))
