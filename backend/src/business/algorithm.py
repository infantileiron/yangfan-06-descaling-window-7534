"""Validate imported work orders and produce one replayable maintenance queue."""

from math import isfinite

from .allocation import queue_order, reserve_shift
from .work_order import ACCESS_TYPES, FIXTURES, GRADES, HARDNESS_BANDS, PRIORITIES
from .estimator import DurationFit


COHORTS = ("训练", "校准", "核验", "待派")
CATEGORY_FIELDS = {
    "cohort": COHORTS,
    "fixture": FIXTURES,
    "hardness_band": HARDNESS_BANDS,
    "access": ACCESS_TYPES,
    "priority": PRIORITIES,
}


def _partition(rows: list[dict]) -> dict[str, list[dict]]:
    groups = {key: [] for key in COHORTS}
    unique_ids = set()
    for row in rows:
        key = row["sample_id"]
        if key in unique_ids:
            raise ValueError(f"工单号 {key} 重复。")
        unique_ids.add(key)
        if any(row[field] not in allowed for field, allowed in CATEGORY_FIELDS.items()):
            raise ValueError(f"{key} 的样本用途、设备类型或巡检分级无法识别。")
        if row["scale_grade"] not in GRADES or row["outlets"] not in range(1, 7) or not 1 <= row["idle_days"] <= 365:
            raise ValueError(f"{key} 的出水口数、维护间隔或目视垢级超出允许范围。")

        group = row["cohort"]
        minutes = row.get("actual_minutes")
        if group == "待派":
            if minutes is not None:
                raise ValueError(f"{key} 是待派工单，请将实际停用时间留空。")
        elif minutes is None or not isfinite(minutes) or not 1 <= minutes <= 720:
            raise ValueError(f"{key} 是完工工单，需填写 1 到 720 分钟的实际停用时间。")
        groups[group].append(row)
    return groups


def analyze(rows: list[dict], parameter: float) -> dict:
    if not isfinite(parameter) or not 30 <= parameter <= 720 or parameter != int(parameter):
        raise ValueError("班次容量需填写 30 到 720 之间的整数分钟数。")
    capacity = int(parameter)
    groups = _partition(rows)
    candidates = sorted(groups["待派"], key=queue_order)
    if not candidates:
        raise ValueError("请至少填写一条带优先级的待派工单。")

    fit = DurationFit.train(groups["训练"], groups["校准"], groups["核验"])
    decisions, assigned, used = reserve_shift(candidates, fit.forecasts(candidates), capacity)
    remainder = capacity - used
    audit_coverage = f"{fit.audit_upper_covered}/{fit.audit_count}"
    return {
        "summary": f"{len(decisions)} 处饮水点中，{assigned} 处排入本班，已预留 {used} 分钟。",
        "metrics": [
            {"label": "本班安排", "value": assigned},
            {"label": "转下一班", "value": len(decisions) - assigned},
            {"label": "本班剩余分钟", "value": remainder},
            {"label": "独立核验 MAE（分钟）", "value": round(fit.audit_mae, 2)},
            {"label": "独立核验上界覆盖", "value": audit_coverage},
        ],
        "rows": decisions,
        "notes": [
            f"使用 {len(groups['训练'])} 条完工工单拟合，"
            f"以 {len(groups['校准'])} 条独立完工工单增加 {fit.buffer:.1f} 分钟校准缓冲。",
            f"独立核验中有 {audit_coverage} 处实际时间落在预留上界内。预留上界用于单处排班，"
            "整班能否按时完成需结合进场情况确认。",
            "时间从本班第一项维修开始累计。班次余量已预先扣除行程、交班和常规巡检。",
        ],
    }
