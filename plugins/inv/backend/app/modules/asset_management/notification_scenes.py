"""资产管理通知场景。"""

PASS_THROUGH = {"title_template": "{title}", "content_template": "{content}"}

SCENES = [
    {
        "scene_key": "asset_handover.pending_receipt",
        "scene_name": "资产交接待接收",
        "module_code": "asset",
        "severity_code": "important",
        "description": "资产交接提交后通知指定的接任教师核对并接收",
        "templates": {"in_app": PASS_THROUGH},
        "routes": [],
    },
    {
        "scene_key": "asset_handover.rejected",
        "scene_name": "资产交接拒收",
        "module_code": "asset",
        "severity_code": "important",
        "description": "接任教师拒收资产后通知交接单提交人处理",
        "templates": {"in_app": PASS_THROUGH},
        "routes": [],
    },
]


__all__ = ["SCENES"]
