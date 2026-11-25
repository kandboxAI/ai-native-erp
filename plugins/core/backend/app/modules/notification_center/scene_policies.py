"""模块登记通知场景策略；底座不预置行业场景。"""
_critical = set()
_in_app_only = set()
_deadlines = {}
_individual_read = set()


def register_scene_policies(critical_scenes, confirmation_scenes, deadline, *, in_app_only_scenes=(), individual_read_scenes=()):
    _critical.update(critical_scenes)
    _in_app_only.update(in_app_only_scenes)
    _individual_read.update(individual_read_scenes)
    for key in confirmation_scenes:
        if key in _deadlines and _deadlines[key] is not deadline:
            raise ValueError(f"重复通知场景策略：{key}")
        _deadlines[key] = deadline


def is_critical_scene(key):
    return key in _critical


def individual_read_scene_keys():
    """需打开正文的场景，不随“全部已读”批量标记。"""
    return frozenset(_individual_read)


def is_in_app_only_scene(key):
    return key in _in_app_only


def confirmation_deadline(key, now):
    callback = _deadlines.get(key)
    return callback(now) if callback else None


def non_message_inbox_scene_keys() -> frozenset[str]:
    """业务专栏内容不在消息页重复展示；不影响生成、投递或审计。

    不缓存：目录收集范围可随插件上下文变化，不能把一次局部收集结果用于其他请求。
    未声明的历史/自定义场景仍归消息，不能按模块前缀或业务 ID 一刀切。
    """
    from .tenant_setup import builtin_scene_specs

    return frozenset(
        spec['scene_key'] for spec in builtin_scene_specs()
        if spec.get('inbox_category', 'message') in {'todo', 'alert', 'announcement', 'family'}
    )


def is_family_inbox_scene(scene_key: str) -> bool:
    from .tenant_setup import builtin_scene_specs

    return any(spec['scene_key'] == scene_key and spec.get('inbox_category') == 'family'
               for spec in builtin_scene_specs())
