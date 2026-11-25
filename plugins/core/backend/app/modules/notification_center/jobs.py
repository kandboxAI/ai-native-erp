"""通知中心的定时任务（由 app.framework.jobs 收集调度）。"""

from app.framework.jobs import PeriodicJob

from .service import process_pending_deliveries_current_tenant

JOBS = [
    # 外部渠道投递：处理待发送的投递记录
    PeriodicJob("notification_center.delivery", 60, process_pending_deliveries_current_tenant),
]
