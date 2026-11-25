"""显式补录现有审批待办，迁移完成后按目标租户运行。"""
import argparse
import asyncio

from app.framework.db.registry import import_all_models
from app.framework.db.session import startup_sqlmodel_database, shutdown_sqlmodel_database, get_session_context
from app.framework.db.tenant import use_tenant_schema, validate_tenant_schema
from app.modules.workflow.runtime.repository import runtime_repository
from app.modules.workflow.todo_service import sync_task


async def backfill(schema):
    import_all_models()
    await startup_sqlmodel_database()
    try:
        with use_tenant_schema(schema):
            async with get_session_context() as session:
                tasks = await runtime_repository.all_pending_todo_tasks(session)
                for task in tasks:
                    await sync_task(session, task)
                await session.commit()
                print(f"租户 {schema} 已核对并补录 {len(tasks)} 项审批任务；重复执行按幂等键去重。")
    finally:
        await shutdown_sqlmodel_database()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="向通用待办补录进行中的历史审批任务（写入指定租户）")
    parser.add_argument("--schema", required=True)
    args = parser.parse_args()
    validate_tenant_schema(args.schema)
    asyncio.run(backfill(args.schema))
