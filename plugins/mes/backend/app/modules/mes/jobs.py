"""框架按已启用 MES 租户执行；迁移就绪后才扫描异常提醒。"""
from app.framework.jobs import PeriodicJob
from .exception_service import exception_service

JOBS=[PeriodicJob("mes.exception.overdue",300,exception_service.remind_overdue)]

from .cnc.worker import run_pending
from .cnc.config import settings


def cnc_jobs(max_concurrent_jobs: int) -> list[PeriodicJob]:
    # 每条通道沿用底座的租户上下文、独立轮询和停止取消机制。
    # 每次只领取一项持久化任务，行锁防止通道/进程重复处理同一任务。
    return [PeriodicJob("mes.cnc.analysis" if index == 0 else f"mes.cnc.analysis.{index + 1}",
        5, run_pending) for index in range(max_concurrent_jobs)]


JOBS.extend(cnc_jobs(settings().max_concurrent_jobs))
