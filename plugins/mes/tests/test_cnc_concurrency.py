"""核价并发配置与真实调度器回归；不访问数据库、文件或外部模型。"""
import asyncio
from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.framework.db.tenant import get_tenant_schema, require_tenant_schema
from app.framework.jobs import JobScheduler
from app.modules.mes import jobs
from app.modules.mes.cnc.config import Settings, settings


def test_default_and_environment_concurrency(monkeypatch):
    monkeypatch.delenv("MES_CNC_MAX_CONCURRENT_JOBS", raising=False)
    assert Settings(_env_file=None).max_concurrent_jobs == 1
    monkeypatch.setenv("MES_CNC_MAX_CONCURRENT_JOBS", "5")
    assert Settings(_env_file=None).max_concurrent_jobs == 5


@pytest.mark.parametrize("value", [0, -1, 17, 1.5])
def test_invalid_concurrency_rejected(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_concurrent_jobs=value)


def test_configured_channels_keep_distinct_keys_and_one_worker_each():
    channels = jobs.cnc_jobs(5)
    assert len(channels) == 5
    assert len({channel.key for channel in channels}) == 5
    assert channels[0].key == "mes.cnc.analysis"
    assert all(channel.run is jobs.run_pending and channel.per_tenant and channel.interval_seconds == 5
        for channel in channels)
    assert len([job for job in jobs.JOBS if job.key.startswith("mes.cnc.analysis")]) == settings().max_concurrent_jobs
    assert len([job for job in jobs.JOBS if job.key == "mes.exception.overdue"]) == 1


def test_five_jobs_run_together_refill_free_channel_and_cancel_cleanly(monkeypatch):
    async def scenario():
        active = set()
        seen = []
        gates = {identifier: asyncio.Event() for identifier in range(1, 12)}
        five_started, sixth_started = asyncio.Event(), asyncio.Event()
        peak = 0

        async def worker():
            nonlocal peak
            identifier = len(seen) + 1
            seen.append((identifier, require_tenant_schema()))
            active.add(identifier)
            peak = max(peak, len(active))
            if len(seen) == 5:
                five_started.set()
            if len(seen) == 6:
                sixth_started.set()
            try:
                await gates[identifier].wait()
            finally:
                active.remove(identifier)

        async def tenants():
            return ["t_test"]

        monkeypatch.setattr(jobs, "run_pending", worker)
        scheduler = JobScheduler([replace(job, interval_seconds=0.01) for job in jobs.cnc_jobs(5)], tenants)
        scheduler.start()
        try:
            await asyncio.wait_for(five_started.wait(), timeout=2)
            assert active == {1, 2, 3, 4, 5}
            gates[1].set()
            await asyncio.wait_for(sixth_started.wait(), timeout=2)
            assert active == {2, 3, 4, 5, 6}
            assert peak == 5 and all(schema == "t_test" for _, schema in seen)
            assert get_tenant_schema() is None
        finally:
            await scheduler.stop()
        assert not active and not scheduler._tasks
        await asyncio.sleep(0.02)
        assert len(seen) == 6
    asyncio.run(scenario())


def test_each_channel_keeps_tenant_context_separate(monkeypatch):
    async def scenario():
        seen = []
        complete = asyncio.Event()

        async def worker():
            schema = require_tenant_schema()
            await asyncio.sleep(0)
            assert require_tenant_schema() == schema
            seen.append(schema)
            if len(seen) == 10:
                complete.set()

        async def tenants():
            return ["t_first", "t_second"]

        monkeypatch.setattr(jobs, "run_pending", worker)
        scheduler = JobScheduler(jobs.cnc_jobs(5), tenants)
        scheduler.start()
        try:
            await asyncio.wait_for(complete.wait(), timeout=2)
        finally:
            await scheduler.stop()
        assert seen.count("t_first") == seen.count("t_second") == 5
        assert get_tenant_schema() is None
    asyncio.run(scenario())
