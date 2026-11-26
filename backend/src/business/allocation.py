"""Reserve a prefix of the approved queue within one technician's shift."""

from .work_order import PRIORITIES


def queue_order(row: dict) -> tuple:
    return PRIORITIES.index(row["priority"]), -row["idle_days"], row["sample_id"]


def reserve_shift(rows: list[dict], forecasts: list[tuple[float, int]], capacity: int) -> tuple:
    assigned_minutes = 0
    assigned_count = 0
    blocked = False
    decisions = []
    for row, (estimate, reserve) in zip(rows, forecasts):
        fits = assigned_minutes + reserve <= capacity
        start = assigned_minutes
        if not blocked and fits:
            assigned_minutes += reserve
            assigned_count += 1
            time_slot = f"{start}–{assigned_minutes} 分"
            decision = "安排本班"
        else:
            time_slot = "未排时段"
            if reserve > capacity:
                decision = "转下一班 · 需整段窗口"
            elif blocked:
                decision = "转下一班 · 保留优先顺序"
            else:
                decision = "转下一班 · 剩余分钟不足"
            blocked = True
        decisions.append(
            {
                "sample_id": row["sample_id"],
                "site": row["site"],
                "priority": row["priority"],
                "estimate": estimate,
                "reserve": reserve,
                "shift_offset": time_slot,
                "decision": decision,
            }
        )
    return decisions, assigned_count, assigned_minutes
