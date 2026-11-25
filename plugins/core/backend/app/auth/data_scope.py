"""数据范围（字典 sys_data_scope）与组织访问方式（字典 sys_org_access_mode）。

代码中不出现任何角色编号：权限检查只看 permission_key，数据范围只看角色上配置的 data_scope_code。
"""

DATA_SCOPE_ALL = "all"
DATA_SCOPE_ORGANIZATION = "organization"
DATA_SCOPE_DEPARTMENT = "department"
DATA_SCOPE_SELF = "self"
DATA_SCOPE_RELATED = "related"

ORG_ACCESS_PRIMARY_ONLY = "primary_only"
ORG_ACCESS_ASSIGNED = "assigned"
ORG_ACCESS_ALL = "all"

ORG_ACCESS_MODE_VALUES = {
    ORG_ACCESS_PRIMARY_ONLY,
    ORG_ACCESS_ASSIGNED,
    ORG_ACCESS_ALL,
}

DATA_SCOPE_VALUES = {
    DATA_SCOPE_ALL,
    DATA_SCOPE_ORGANIZATION,
    DATA_SCOPE_DEPARTMENT,
    DATA_SCOPE_SELF,
    DATA_SCOPE_RELATED,
}

DATA_SCOPE_PRIORITY = {
    DATA_SCOPE_SELF: 1,
    DATA_SCOPE_RELATED: 1,
    DATA_SCOPE_DEPARTMENT: 2,
    DATA_SCOPE_ORGANIZATION: 3,
    DATA_SCOPE_ALL: 4,
}


def normalize_data_scope(scope: str | None) -> str:
    if scope in DATA_SCOPE_VALUES:
        return scope
    return DATA_SCOPE_ORGANIZATION


def normalize_org_access_mode(mode: str | None) -> str:
    if mode in ORG_ACCESS_MODE_VALUES:
        return mode
    return ORG_ACCESS_PRIMARY_ONLY


def merge_data_scopes(scopes: list[str]) -> str:
    if not scopes:
        return DATA_SCOPE_ORGANIZATION
    return max((normalize_data_scope(scope) for scope in scopes), key=lambda item: DATA_SCOPE_PRIORITY[item])


def effective_data_scope(permission_key: str, permission_scopes: dict[str, str] | None) -> str | None:
    """返回某个权限上配置的数据范围（角色权限上的 data_scope_code，为空时取角色的）。"""
    if not permission_scopes:
        return None
    scope = permission_scopes.get(permission_key)
    if scope is None:
        return None
    return normalize_data_scope(scope)
