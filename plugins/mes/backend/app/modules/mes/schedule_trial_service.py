"""MES只读自动试排；快照读取完成并释放连接后，在可终止子进程内计算。"""
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys

from app.auth.scope_filters import resolve_write_org_id
from app.core.exceptions import AppException
from app.framework.db.models import utc_now
from app.framework.db.session import get_session_context
from .schedule_trial_planning import build_problem, prepare, snapshot_key
from .schedule_trial_repository import repository
from .schedule_limits import MODEL_OVERHEAD_SECONDS

_active_solves = 0


async def run_solver(problem):
    global _active_solves
    # 每个Web进程最多两次试排，拒绝无界排队；CP-SAT每次仅使用一个计算线程。
    if _active_solves >= 2:
        raise AppException("当前试排繁忙，请稍后重试", 429)
    _active_solves += 1
    process = None
    communication = None
    try:
        environment = {k: v for k, v in os.environ.items() if k.upper() in {
            "SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "LANG", "LC_ALL"}}
        # uvicorn在Windows reload下可能使用Selector事件循环；不依赖其不支持的async subprocess。
        process = subprocess.Popen([sys.executable, "-X", "utf8", str(Path(__file__).with_name("schedule_solver.py"))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=environment,
            **({"creationflags": 0x08000000} if os.name == "nt" else {}))
        communication = asyncio.create_task(asyncio.to_thread(process.communicate, json.dumps(problem).encode(),
            timeout=problem["time_limit_seconds"] + MODEL_OVERHEAD_SECONDS))
        output, _ = await asyncio.shield(communication)
        if process.returncode:
            raise AppException("排程引擎执行失败，请确认已安装当前后端依赖", 500)
        return json.loads(output)
    except subprocess.TimeoutExpired:
        return dict(status_code="UNKNOWN", segments=[], completions=[])
    finally:
        try:
            if process and process.poll() is None:
                process.kill()
                if communication and not communication.done():
                    await asyncio.shield(communication)
                else:
                    await asyncio.to_thread(process.communicate)
        finally:
            _active_solves -= 1


def authorize(scope, user):
    if "mes" not in user.enabled_plugin_keys or "mes:schedule:manage" not in user.permissions:
        raise AppException("缺少MES排程管理权限或租户未启用MES", 403)
    resolve_write_org_id(user, scope.org_id, "mes:schedule:manage")
    if scope.start_at < utc_now() - timedelta(minutes=1):
        raise AppException("试排开始时间不能早于当前时间，请调整试排窗口", 422)


class TrialService:
    async def prepare(self, scope, user):
        authorize(scope, user)
        async with get_session_context() as session:
            snapshot = await repository.snapshot(session, scope, user)
            return prepare(snapshot, scope)

    async def solve(self, request, user):
        authorize(request, user)
        async with get_session_context() as session:
            snapshot = await repository.snapshot(session, request, user)
            if request.snapshot_key != snapshot_key(snapshot):
                raise AppException("工单或资源资料已变化，请重新读取并核对试排资料", 409)
            problem, issues, labels = build_problem(snapshot, request)
            captured_at = utc_now()
        # 不持有数据库连接、事务或行锁等待求解，不写planned_*、派工、报工或检验事实。
        if issues:
            return dict(status_code="PRECHECK_FAILED", issues=issues, segments=[], completions=[])
        result = await run_solver(problem)
        return format_result(result, request, labels, captured_at)


def format_result(result, request, labels, captured_at):
        for segment in result["segments"]:
            segment.update(start_at=request.start_at + timedelta(minutes=segment.pop("start")),
                end_at=request.start_at + timedelta(minutes=segment.pop("end")),
                work_order_no=labels["order"][segment["order_id"]], operation_name=labels["operation"][segment["operation_id"]],
                person_no=labels["person"].get(segment["person_id"]), equipment_name=labels["equipment"].get(segment["equipment_id"]))
        for row in result.get("completions", []):
            row.update(work_order_no=labels["order"][row["work_order_id"]])
            for key in ("first_article_release", "inspection_release", "due"):
                row[f"{key}_at"] = request.start_at + timedelta(minutes=row.pop(key))
            shipping=row.pop("shipping_release",None)
            row["shipping_release_at"]=request.start_at+timedelta(minutes=shipping) if shipping is not None else None
        return result | dict(issues=[], snapshot_key=request.snapshot_key, captured_at=captured_at,
            warnings=["结果以首件及最终检验合格、就绪时间及常规日历确认条件成立为前提。",
                "未评估整单齐套、出货准备及发货窗口；仅预测检验放行，不承诺出货。",
                "旧人工计划按独占资源保守避让；本次不写入生产计划，不产生派工或质量放行。"])


service = TrialService()
