"""消息总线的定时任务（由 app.framework.jobs 收集调度）。"""

from app.framework.jobs import PeriodicJob

from .service import publish_pending_current_tenant

JOBS = [
    # 事件出站：发布 int_outbox_event 中待发送的事件
    PeriodicJob("message_bus.outbox", 30, publish_pending_current_tenant),
]
