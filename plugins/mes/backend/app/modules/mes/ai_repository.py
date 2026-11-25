"""AI 制造查询复用生产事实的父单据存活规则。"""

from sqlalchemy import exists, select

from .models import MesProductionReport, MesWorkOrder, MesWorkOrderOperation


def related_alive_conditions(model, _user) -> tuple:
    if model is MesWorkOrderOperation:
        return (exists(select(MesWorkOrder.id).where(
            MesWorkOrder.id == model.work_order_id, MesWorkOrder.deleted_at.is_(None),
        )),)
    if model is MesProductionReport:
        return (exists(select(MesWorkOrderOperation.id).join(
            MesWorkOrder, MesWorkOrder.id == MesWorkOrderOperation.work_order_id,
        ).where(MesWorkOrderOperation.id == model.operation_id,
                MesWorkOrderOperation.deleted_at.is_(None), MesWorkOrder.deleted_at.is_(None))),)
    return ()
