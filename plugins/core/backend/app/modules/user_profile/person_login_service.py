"""在调用方事务内为人员开通或关联账号，不重置现有密码或组织配置。"""
import re
import secrets
import string

from app.core.exceptions import AppException
from app.auth.scope_filters import resolve_write_org_id
from app.modules.masterdata import service as people
from app.modules.masterdata.repository import repository as person_repository
from .person_login_repository import repository
from .provisioning import ensure_tenant_user, assign_roles


def normalize_login_mobile(value):
    mobile = "".join(str(value or "").split())
    if not re.fullmatch(r"\+?[0-9]{6,20}", mobile):
        raise AppException("请填写有效的登录手机号，用于自动开通或关联账号", 422)
    return mobile


def generate_initial_password():
    """16位随机密码，确保包含字母、数字和符号，兼容登录页8–18位规则。"""
    alphabet = string.ascii_letters + string.digits + "!@#$%*_-+="
    chars = [secrets.choice(string.ascii_letters), secrets.choice(string.digits), secrets.choice("!@#$%*_-+=")]
    chars.extend(secrets.choice(alphabet) for _ in range(13))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def normalize_account_email(value):
    email = str(value or "").strip().lower()
    if email and (len(email) > 255 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
        raise AppException("请填写有效的邮箱地址", 422)
    return email or None


async def sync_person_login_details(session, *, user_id, email, role_nos, actor, permission):
    """在业务事务内同步账号邮箱和追加角色；不移除其他入口授予的角色。"""
    user = await repository.user_by_id(session, user_id)
    auth = await repository.auth_for_user(session, user) if user else None
    if auth is None:
        raise AppException("关联账号不存在，请联系管理员核对", 409)
    user_id = user.id
    email = auth.email if email is ... else normalize_account_email(email)
    email_changed = email != auth.email
    missing = set(role_nos) - await repository.user_roles(session, user_id)
    if not email_changed and not missing:
        return
    if permission not in actor.permissions or await repository.accessible_user(session, user_id, actor, permission) is None:
        raise AppException("同步账号邮箱或班主任角色需要教师账号开通与关联权限", 403)
    membership = await repository.membership(session, auth.id, actor.tenant_id)
    if not user.is_active or not auth.is_active or membership is None or not membership.is_active:
        raise AppException("关联账号已停用或未获准进入当前学校，请先核对账号状态", 409)
    if missing - await repository.active_roles(session, missing):
        raise AppException("登录角色尚未配置或已停用，请联系管理员配置后重试", 409)
    if email_changed:
        if not email and not auth.mobile:
            raise AppException("该账号仅使用邮箱登录，不能清空邮箱", 422)
        if email:
            await repository.lock_email(session, email)
            other = await repository.auth_by_email(session, email)
            if other is not None and other.id != auth.id:
                raise AppException("该邮箱已被其他账号使用，请核对后重试", 409)
        await repository.update_email(session, auth, email, actor.auth_user_id)
    if missing:
        await assign_roles(session, user_id, sorted(missing), created_by=actor.user_id)


async def account_briefs(session, user_ids):
    """业务身份已鉴权后的只读契约：邮箱、掩码手机号和账号状态，不提供凭据。"""
    return await repository.account_briefs(session, user_ids)


async def ensure_person_login(session, *, person, mobile, selected_user_id, full_name,
                              org_id, actor, permission, role_nos):
    """调用方先校验业务写权限、账号维护权限及目标组织范围；不单独提交。"""
    if permission not in actor.permissions:
        raise AppException("没有开通或关联账号的权限", 403)
    org_id = resolve_write_org_id(actor, org_id, permission)
    if set(role_nos) - await repository.active_roles(session, role_nos):
        raise AppException("登录角色尚未配置或已停用，请联系管理员配置后重试", 409)
    is_recreating = False
    if selected_user_id:
        user = await repository.accessible_user(session, selected_user_id, actor, permission)
        if user is None:
            raise AppException("所选账号不存在、已删除或超出可维护范围", 409)
        auth = await repository.auth_for_user(session, user)
        if auth is None:
            raise AppException("所选账号的登录身份不存在，请联系管理员核对", 409)
    else:
        mobile = normalize_login_mobile(mobile)
        await repository.lock_mobile(session, mobile)
        auth = await repository.auth_by_mobile(session, mobile)
        user = await repository.user_by_auth(session, auth.id) if auth else None
        if user is not None:
            accessible = await repository.accessible_user(session, user.id, actor, permission,
                include_deleted=user.deleted_at is not None)
            if accessible is None:
                raise AppException("该手机号对应账号不在可维护范围内，请联系账号管理员核对", 409)
            if user.deleted_at is not None:
                if user.display_name.strip() != full_name.strip():
                    raise AppException("该手机号的历史账号姓名与当前姓名不一致，请核对手机号或联系账号管理员处理", 409)
                is_recreating = True
                user = None
    if auth is not None:
        if not auth.is_active or (user is not None and (not user.is_active or user.deleted_at is not None)):
            raise AppException("登录账号已停用，请在系统用户中核对账号状态", 409)
        membership = await repository.membership(session, auth.id, actor.tenant_id)
        if membership is None or (not membership.is_active and not is_recreating):
            raise AppException("该账号尚未获准进入当前学校，请由账号管理员处理租户成员关系", 409)
    holders = await person_repository.persons_bound_to_user(session, user.id) if user else []
    if len(holders) > 1:
        raise AppException("该账号关联了多份人员资料，请先在用户模块核对", 409)
    holder = holders[0] if holders else None
    if holder is not None and holder.full_name.strip() != full_name.strip():
        raise AppException("账号关联人员的姓名与教师姓名不一致，请核对手机号或所选账号", 409)
    if person is None:
        person = holder
    elif person.user_id not in (None, user.id if user else None):
        raise AppException("教师已有其他登录账号，不能通过普通保存自动更换", 409)
    if holder is not None and person is not None and holder.party_id != person.party_id:
        await people.release_account_placeholder(session, holder.party_id, actor_id=actor.user_id)
    password = generate_initial_password() if auth is None else ""
    if user is None:
        user, person = await ensure_tenant_user(
            session, tenant_id=actor.tenant_id, org_id=org_id, display_name=full_name,
            mobile=mobile, password=password, role_nos=role_nos, person=person,
            created_by=actor.user_id, auth_actor_id=actor.auth_user_id, is_password_change_required=True)
        if is_recreating and not membership.is_active:
            await repository.reactivate_membership(session, membership, actor.auth_user_id)
    else:
        if person is None:
            person = await person_repository.create_person(session, full_name=full_name, user_id=user.id, created_by=actor.user_id)
        else:
            await people.bind_person_login_user(session, party_id=person.party_id, user_id=user.id, actor_id=actor.user_id)
        await assign_roles(session, user.id, role_nos, created_by=actor.user_id)
    return user, {"status": "created" if password else "linked", "login_mobile": auth.mobile if auth else mobile,
                  **({"initial_password": password} if password else {})}
