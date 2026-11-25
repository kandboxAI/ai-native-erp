"""逐道工序的必要产能条件；只证明明显不可能，不代替完整CP-SAT求解。"""


def available_minutes(windows):
    """资格与日历可能给出重叠区间，按并集计算，不能重复累加。"""
    total = 0
    end = None
    for start, finish in sorted(windows):
        if finish <= start:
            continue
        total += max(0, finish - max(start, end if end is not None else start))
        end = max(end if end is not None else finish, finish)
    return total


def capacity_issues(orders, labels):
    issues = []

    def check(operation, title, count):
        if operation["kind"] != "external":
            required = count * (operation["run"] + operation["load"] + operation["unload"])
            required += operation["setup"]
            shortages = []
            # 同一道工序在首件与剩余批量固定人员；一人两机不会缩短本工序的逐件耗时。
            key = "auto" if operation.get("lunch") else "work"
            people = operation["people"]
            if people:
                capacity = max(available_minutes(p[key]) for p in people)
                if required > capacity:
                    shortages.append(f"候选人员最多可用{capacity}分钟")
            machines = operation["machines"]
            if operation["kind"] == "machine" and machines:
                capacity = max(available_minutes(m["work"]) for m in machines)
                if required > capacity:
                    shortages.append(f"单台候选设备最多可用{capacity}分钟")
            if shortages:
                issues.append(f"{title}：安排{count}件，含准备和装卸至少需要{required}分钟；{'，'.join(shortages)}。"
                    "本工序固定人员和设备，不按候选数量累加产能；请核对单件工时或排程窗口")
        if operation.get("after_inspection"):
            check(operation["after_inspection"], title + " / 独立检验", count)

    for order in orders:
        count = order["quantity"] - (1 if order.get("remaining_only") else 0)
        if count <= 0:
            continue
        name = labels["order"].get(order["id"], "工单")
        for index, operation in enumerate(order["operations"], 1):
            operation_name = labels["operation"].get(operation["id"], "工序")
            check(operation, f"{name} / 第{index}道 {operation_name}", count)
        if order.get("inspection"):
            # 独立的首件检验与最终检验可分别选择资源，不能错误要求由同一人完成全部件数。
            for key, quantity in (("首件检验", 0 if order.get("remaining_only") else 1), ("最终检验", order["quantity"] - 1)):
                if quantity > 0:
                    check(order["inspection"], f"{name} / {key}", quantity)
    return issues
