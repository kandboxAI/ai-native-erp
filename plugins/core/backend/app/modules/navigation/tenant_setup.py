from .repository import retire_obsolete_menus, sync_consumable_requisition_menu


async def setup_tenant(session, ctx):
    await retire_obsolete_menus(session)
    await sync_consumable_requisition_menu(session)
