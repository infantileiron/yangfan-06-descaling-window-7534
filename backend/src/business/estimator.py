"""Estimate center durations and independently verify calibrated upper durations."""

from dataclasses import dataclass
from math import ceil

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from .work_order import ACCESS_TYPES, FIXTURES, HARDNESS_BANDS


COVERAGE = 0.90


def _expert_features(row: dict) -> list:
    # Encode fixture as flags to avoid imposing an ordering between machine designs.
    fixture_flags = [int(row["fixture"] == fixture) for fixture in FIXTURES]
    return fixture_flags + [
        row["outlets"],
        row["idle_days"],
        HARDNESS_BANDS.index(row["hardness_band"]),
        row["scale_grade"],
        ACCESS_TYPES.index(row["access"]),
    ]


def _inputs(rows: list[dict]) -> np.ndarray:
    return np.asarray([_expert_features(row) for row in rows], dtype=float)


def _minutes(rows: list[dict]) -> np.ndarray:
    return np.asarray([row["actual_minutes"] for row in rows], dtype=float)


@dataclass(frozen=True)
class DurationFit:
    model: HistGradientBoostingRegressor
    buffer: float
    audit_mae: float
    audit_upper_covered: int
    audit_count: int

    @classmethod
    def train(cls, history: list[dict], calibration: list[dict], audit: list[dict]) -> "DurationFit":
        if len(history) < 40 or len(calibration) < 20 or len(audit) < 15:
            raise ValueError("请准备至少 40 条训练、20 条校准及 15 条独立核验工单。")
        if len({row["actual_minutes"] for row in history}) < 2:
            raise ValueError("训练工单的实际停用时长相同，无法拟合工时差异。")

        estimator = HistGradientBoostingRegressor(
            learning_rate=0.10,
            max_iter=120,
            max_leaf_nodes=12,
            min_samples_leaf=10,
            l2_regularization=1.0,
            early_stopping=False,
            random_state=112506,
        )
        estimator.fit(_inputs(history), _minutes(history))
        holdout_center = cls.predict(estimator, calibration)
        signed_residual = np.sort(_minutes(calibration) - holdout_center)
        rank = ceil((len(calibration) + 1) * COVERAGE)
        buffer = max(0.0, float(signed_residual[rank - 1]))

        audit_center = cls.predict(estimator, audit)
        audit_actual = _minutes(audit)
        mae = float(np.abs(audit_actual - audit_center).mean())
        covered = int((audit_actual <= np.ceil(audit_center + buffer)).sum())
        return cls(estimator, buffer, mae, covered, len(audit))

    @staticmethod
    def predict(estimator: HistGradientBoostingRegressor, rows: list[dict]) -> np.ndarray:
        return np.maximum(1, estimator.predict(_inputs(rows)))

    def forecasts(self, rows: list[dict]) -> list[tuple[float, int]]:
        estimates = self.predict(self.model, rows)
        return [(round(float(estimate), 1), ceil(float(estimate) + self.buffer)) for estimate in estimates]
