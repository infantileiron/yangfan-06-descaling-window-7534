"""Deterministic records for completed and pending facility visits."""

from random import Random


from .work_order import ACCESS_TYPES, FIXTURES, GRADES, HARDNESS_BANDS, PRIORITIES


SITES = (
    "槐行广场西侧", "钟望绿道岔口", "顺桥服务点", "银湾巷口", "杨街候车廊", "合风公园北门",
    "万菱路志愿站", "桃埂服务角", "左池公交亭", "花栈街角", "迴廊访客台", "渚心广场南门",
)


def _record(sample_id, site, cohort, fixture, outlets, idle_days, hardness, grade, access, priority):
    return {
        "sample_id": sample_id,
        "site": site,
        "cohort": cohort,
        "fixture": fixture,
        "outlets": outlets,
        "idle_days": idle_days,
        "hardness_band": hardness,
        "scale_grade": grade,
        "access": access,
        "priority": priority,
        "actual_minutes": None,
    }


def demo_rows() -> list[dict]:
    rng = Random(112506)
    rows = []
    base_fixture = dict(zip(FIXTURES, (0, 7, 16)))
    hardness_steps = dict(zip(HARDNESS_BANDS, (0, 1, 2)))
    for cohort, prefix, count in (("训练", "T", 168), ("校准", "C", 36), ("核验", "V", 36)):
        for i in range(count):
            fixture = rng.choice(FIXTURES)
            outlets = rng.randint(1, 4)
            days = rng.randint(15, 200)
            hardness = rng.choice(HARDNESS_BANDS)
            grade = rng.choices(GRADES, weights=(1, 3, 5, 4, 3), k=1)[0]
            access = rng.choice(ACCESS_TYPES)
            row = _record(
                f"QL-{prefix}{i + 1:03d}", rng.choice(SITES), cohort, fixture, outlets,
                days, hardness, grade, access, rng.choice(PRIORITIES),
            )
            minutes = (
                12 + base_fixture[fixture] + 6 * outlets + 0.085 * days + 2.4 * grade ** 2
                + 2 * hardness_steps[hardness] * grade + 7 * (access == "前台登记")
                + 11 * (fixture == "落地式" and outlets >= 3 and grade >= 3)
                + rng.gauss(0, 3 + 1.1 * grade)
            )
            row["actual_minutes"] = max(1, round(minutes))
            rows.append(row)
    pending = (
        ("落地式", 3, 145, "高", 4, "前台登记", "高"),
        ("台面式", 2, 102, "中", 2, "直接进场", "高"),
        ("壁挂式", 2, 118, "高", 3, "直接进场", "中"),
        ("落地式", 4, 95, "中", 3, "前台登记", "中"),
        ("台面式", 2, 70, "低", 2, "前台登记", "中"),
        ("壁挂式", 1, 18, "低", 0, "直接进场", "常规"),
        ("壁挂式", 1, 50, "中", 1, "直接进场", "常规"),
        ("台面式", 3, 48, "中", 1, "前台登记", "常规"),
    )
    rows.extend(_record(f"QL-P{i:02d}", site, "待派", *inputs)
                for i, (site, inputs) in enumerate(zip(SITES, pending), 1))
    return rows
