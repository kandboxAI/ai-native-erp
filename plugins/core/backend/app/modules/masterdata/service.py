"""人员主数据公开写入能力。

调用方必须先校验所属业务身份的操作权限和数据范围；不接受客户端任意
party_id 直接写入。复用调用方会话，flush 后由完整业务动作统一提交。
"""
from .repository import repository


async def existing_person_names(session, *, names):
    """已授权建档动作的精确重名预检；调用方先校验业务权限和范围。

    人员在租户内共享，此契约仅对调用方提交的姓名返回重名集合，用于拒绝自动重复建档；
    不返回现有人员 ID、联系方式或账号，不将同名作为自动复用身份的证据。
    """
    if len(names) > 100:
        raise ValueError("单次人员重名预检最多100项")
    return await repository.existing_person_names(session, names)

async def bind_person_login_user(session, *, party_id, user_id, actor_id, replace_existing=False):
    """关联现有租户账号；调用方先校验业务对象和目标用户的权限及数据范围。

    不创建或修改账号。默认拒绝占用冲突；业务方显式替换关联时，仅解除
    旧人员的user_id，保留旧人员及其业务记录。同一事务锁定目标用户，
    避免并发重复绑定。提交由完整业务动作负责。
    """
    from app.core.exceptions import AppException
    from app.modules.user_profile.repository import repository as users

    person = await repository.get_person(session, party_id)
    if person is None:
        raise AppException("人员档案不存在或已删除", 409)
    if user_id is not None:
        user = await users.get(session, user_id, for_update=True)
        if user is None or not user.is_active:
            raise AppException("所选账号不存在、已删除或已停用，请重新选择", 409)
        holders = await repository.persons_bound_to_user(session, user_id)
        others = [holder for holder in holders if holder.party_id != party_id]
        if others and not replace_existing:
            raise AppException("所选账号已关联其他人员，不能重复绑定；请先核对并解除原人员关联", 409)
        for holder in others:
            await repository.set_person_user(session, holder, None, actor_id)
    if person.user_id != user_id:
        await repository.set_person_user(session, person, user_id, actor_id)


async def create_person(session, *, full_name, mobile, actor_id, gender_code=None, email=None):
    person = await repository.create_person(session, full_name=full_name, gender_code=gender_code, created_by=actor_id)
    await repository.set_primary_contact(session, person.party_id, "mobile", mobile, updated_by=actor_id)
    if email:
        await repository.set_primary_contact(session, person.party_id, "email", email, updated_by=actor_id)
    return person


async def update_person_contact(session, *, party_id, changes, actor_id):
    person = await repository.get_person(session, party_id)
    if person is None:
        from app.core.exceptions import AppException
        raise AppException("人员档案不存在", 409)
    if "full_name" in changes:
        await repository.rename_person(session, person, changes["full_name"], updated_by=actor_id)
    if "mobile" in changes:
        await repository.set_primary_contact(session, party_id, "mobile", changes["mobile"], updated_by=actor_id)
    if "email" in changes:
        await repository.set_primary_contact(session, party_id, "email", changes["email"], updated_by=actor_id)
    if "gender_code" in changes:
        await repository.set_person_gender(session, person, changes["gender_code"], updated_by=actor_id)


async def release_account_placeholder(session, party_id, *, actor_id):
    """仅解除无业务引用的账号初始化人员；不删除人员、不移动业务记录。"""
    from app.core.exceptions import AppException
    person = await repository.get_person(session, party_id)
    if person is None or not await repository.is_account_placeholder(session, person):
        raise AppException("账号已关联其他实际人员或历史业务，请在系统用户中核对关联，不能自动覆盖", 409)
    await repository.set_person_user(session, person, None, actor_id)
