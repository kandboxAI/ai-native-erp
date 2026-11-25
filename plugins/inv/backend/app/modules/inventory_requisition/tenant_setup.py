"""领用开通不按学校角色自动授权，也不创建组织专属的仓库和分类。

权限和菜单由底座目录同步授予内置管理员；其他成员通过正常授权能力分配。
仓库、库位及物料分类由库存模块维护，演示记录通过 demo_seed 显式加载。
"""


async def setup_tenant(session, ctx) -> None:
    # This module currently has no additional mandatory tenant configuration.
    pass


__all__ = ["setup_tenant"]
