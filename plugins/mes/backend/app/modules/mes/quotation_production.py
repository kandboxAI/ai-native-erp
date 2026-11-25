"""将已采用的不可变核价工艺转换为可编辑生产配置；不使用最新 AI 任务结果。"""
from decimal import Decimal, ROUND_HALF_UP

from pydantic import ValidationError

from app.core.exceptions import AppException
from .cnc.schemas import Operation
from .schemas import WorkOrderOperationCreate
from .operation_planning import MAX_PLAN_MINUTES


def production_operations(snapshot, drawing_no, quantity=Decimal(1)):
    if snapshot is None:
        return []
    if not isinstance(snapshot, list) or len(snapshot) > 100:
        raise AppException(f"{drawing_no}：已采用的报价工艺格式异常，请核对来源报价", 409)
    operations = []
    try:
        for index, raw in enumerate(snapshot, 1):
            operation = Operation.model_validate(raw)
            # CNC 明确保存小时/件；生产配置保存分钟/件，整批时长由本次生产数量计算。
            minutes = None
            if operation.unit_hours is not None and operation.unit_hours > 0:
                minutes = max(Decimal("0.001"), (operation.unit_hours * 60).quantize(
                    Decimal("0.001"), rounding=ROUND_HALF_UP))
            description = ["来源：工程已采用的报价工艺，生产前请复核。"]
            if operation.machine:
                description.append(f"建议设备：{operation.machine}")
            description.extend(filter(None, (operation.note, operation.estimate_basis)))
            if minutes is None:
                description.append("未提供加工工时，请配置生产工时；委外周期另行确认。")
            operations.append(WorkOrderOperationCreate(
                operation_no=str(index * 10), operation_name=operation.name,
                standard_minutes_per_unit=minutes,
                is_quality_required=operation.process_type_code == "inspection",
                operation_description="\n".join(description),
            ))
    except (ValidationError, ValueError, TypeError, ArithmeticError) as error:
        raise AppException(f"{drawing_no}：已采用的报价工艺格式或工时无效，请核对后再生成生产工单", 409) from error
    if sum((op.standard_minutes_per_unit * quantity for op in operations
            if op.standard_minutes_per_unit is not None), Decimal(0)) > MAX_PLAN_MINUTES:
        raise AppException(f"{drawing_no}：报价工时乘本次数量后超过10年，请先核对工时", 409)
    return operations
