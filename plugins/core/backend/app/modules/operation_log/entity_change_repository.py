"""业务实体字段变更公开契约；只追加，复用调用者事务，不读取请求体。

字段白名单、目标范围由拥有者提供；本模块不含行业规则，不提交业务事务。
"""
import json
from sqlalchemy import func, or_, and_, false, true
from sqlmodel import select
from app.modules.operation_log.models import AuditOperationLog
from app.modules.user_profile.models import SysUser
from app.auth.scope_filters import org_column_scope_condition, resolve_effective_data_scope


def prefix(entity_key):
    return '{"kind":"entity_change_v1","entity_key":' + json.dumps(entity_key) + ','


def append_change(session, *, module_code, entity_key, target_id, org_id, user, action, target_label, changes,
                  target_owner_id=None):
    if not changes:
        return
    payload = {'kind': 'entity_change_v1', 'entity_key': entity_key,
               'target_label': target_label, 'actor_name': user.display_name,
               'changes': changes, 'target_owner_id': str(target_owner_id) if target_owner_id else None}
    session.add(AuditOperationLog(
        org_id=org_id, module_code=module_code, target_type_code=module_code,
        target_id=target_id, actor_user_id=user.user_id, created_by=user.user_id,
        action_code=action, content=json.dumps(payload, ensure_ascii=False, separators=(',', ':')),
    ))


async def query_changes(session, *, module_code, entity_key, target_table, scope, user, permission, item_id=None,
                        actor=None, start=None, end=None, page=1, page_size=20):
    # Caller supplies the real owning target and scope; include archived targets but never unrelated logs.
    log = AuditOperationLog
    data_scope = resolve_effective_data_scope(user, permission)
    removed_scope = true() if data_scope in {'all', 'organization'} else false()
    if data_scope == 'self':
        removed_scope = log.content.contains('"target_owner_id":' + json.dumps(str(user.user_id)), autoescape=True)
    # Physical deletes have no row to join. All/org use the immutable log org;
    # self additionally requires the original owner snapshot. Related remains denied.
    visibility = or_(and_(*(scope or [true()])), and_(target_table.id.is_(None), removed_scope))
    statement = select(log, SysUser.display_name).outerjoin(
        target_table, target_table.id == log.target_id,
    ).outerjoin(SysUser, SysUser.id == log.actor_user_id).where(
        log.module_code == module_code, log.target_type_code == module_code,
        log.content.startswith(prefix(entity_key)), visibility,
    )
    org_scope = org_column_scope_condition(log.org_id, user, permission)
    if org_scope is not None:
        statement = statement.where(org_scope)
    if item_id:
        statement = statement.where(log.target_id == item_id)
    if actor:
        # Snapshot names remain searchable after a user's display name changes.
        statement = statement.where(or_(
            log.content.contains('"actor_name":' + json.dumps(actor, ensure_ascii=False), autoescape=True),
            SysUser.display_name == actor))
    if start:
        statement = statement.where(log.created_at >= start)
    if end:
        statement = statement.where(log.created_at <= end)
    total = int((await session.exec(select(func.count()).select_from(statement.subquery()))).one())
    rows = (await session.exec(statement.order_by(log.created_at.desc(), log.id.desc())
                              .offset((page - 1) * page_size).limit(page_size))).all()
    result = []
    for row, actor_name in rows:
        payload = json.loads(row.content)
        result.append({'id': str(row.id), 'target_id': str(row.target_id),
                       'target_label': payload['target_label'], 'action': row.action_code,
                       'actor_name': payload.get('actor_name') or actor_name or '原操作人已停用',
                       'changed_at': row.created_at, 'changes': payload['changes']})
    return {'list': result, 'total': total, 'page': page, 'page_size': page_size}
