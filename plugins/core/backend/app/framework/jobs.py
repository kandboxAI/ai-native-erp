"""定时后台任务：模块声明，框架收集与调度。

模块在 ``jobs.py`` 中声明 ``JOBS``，只写“多久跑一次、做什么”：

    from app.framework.jobs import PeriodicJob

    JOBS = [PeriodicJob("education.lesson_evaluation.reminder", 900, lesson_evaluation_service.send_due_reminders)]

框架负责：
- 每个任务一个 asyncio task，启动后立即执行一次，之后按间隔循环；
- ``per_tenant=True`` 时按租户循环，每个租户在 ``use_tenant_schema`` 中调用 ``run``，``run`` 只处理当前租户；
- 单个租户失败只记录日志，不影响其他租户和下一轮；
- 进程停止时统一取消。

租户列表由应用入口注入（``start_jobs(list_tenant_schemas)``），框架不依赖租户目录的实现。
能力包任务按模块归属在租户循环中跳过未启用的租户。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, replace

from app.framework.catalog import iter_module_attr
from app.framework.db.tenant import use_tenant_schema

logger = logging.getLogger(__name__)

TenantSchemaLister = Callable[[], Awaitable[list[str]]]


@dataclass(frozen=True)
class PeriodicJob:
    key: str  # 稳定的程序标识，全局唯一，如 education.lesson_evaluation.reminder
    interval_seconds: float  # 两轮之间的间隔（秒），从上一轮结束开始计
    run: Callable[[], Awaitable[object]]  # per_tenant=True 时只处理当前租户
    per_tenant: bool = True
    plugin_key: str | None = None  # 收集时从模块清单推断，L1 任务保持 None


def collect_jobs(only: set[str] | None = None) -> list[PeriodicJob]:
    """收集 app.modules.*.jobs 中声明的 JOBS；only 限定模块目录名。"""
    from app.framework.deployment import module_plugin_owner

    def owner(module) -> str | None:
        parts = getattr(module, "__name__", "").split(".")
        return module_plugin_owner(parts[2]) if len(parts) > 2 else None

    jobs = [
        replace(job, plugin_key=owner(module))
        for module in iter_module_attr("jobs", only)
        for job in getattr(module, "JOBS", [])
    ]
    keys = [job.key for job in jobs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"定时任务 key 重复：{', '.join(duplicates)}")
    return jobs


async def run_job_once(job: PeriodicJob, list_tenant_schemas: TenantSchemaLister) -> None:
    """执行一轮。按租户执行时，单个租户的异常记录后继续下一个租户。"""
    if not job.per_tenant:
        await job.run()
        return
    for schema in await list_tenant_schemas():
        try:
            if job.plugin_key:
                from app.framework.tenant_plugins import is_plugin_enabled_for_schema

                if not await is_plugin_enabled_for_schema(schema, job.plugin_key):
                    continue
            with use_tenant_schema(schema):
                await job.run()
        except Exception:  # noqa: BLE001 - 单个租户失败不影响其他租户
            logger.exception("job %s failed for %s", job.key, schema)


class JobScheduler:
    def __init__(self, jobs: list[PeriodicJob], list_tenant_schemas: TenantSchemaLister) -> None:
        self._jobs = jobs
        self._list_tenant_schemas = list_tenant_schemas
        self._tasks: list[asyncio.Task] = []

    async def _loop(self, job: PeriodicJob) -> None:
        while True:
            try:
                await run_job_once(job, self._list_tenant_schemas)
            except Exception:  # noqa: BLE001 - 一轮失败不终止任务
                logger.exception("job %s failed", job.key)
            await asyncio.sleep(job.interval_seconds)

    def start(self) -> None:
        if self._tasks:
            return
        self._tasks = [asyncio.create_task(self._loop(job), name=f"job:{job.key}") for job in self._jobs]
        logger.info("started %d jobs: %s", len(self._jobs), ", ".join(job.key for job in self._jobs))

    async def stop(self) -> None:
        tasks, self._tasks = self._tasks, []
        for task in reversed(tasks):
            task.cancel()
        for task in reversed(tasks):
            with suppress(asyncio.CancelledError):
                await task


_scheduler: JobScheduler | None = None


def start_jobs(list_tenant_schemas: TenantSchemaLister) -> None:
    global _scheduler
    if _scheduler is None:
        _scheduler = JobScheduler(collect_jobs(), list_tenant_schemas)
    _scheduler.start()


async def stop_jobs() -> None:
    global _scheduler
    if _scheduler is None:
        return
    await _scheduler.stop()
    _scheduler = None


__all__ = ["JobScheduler", "PeriodicJob", "collect_jobs", "run_job_once", "start_jobs", "stop_jobs"]
