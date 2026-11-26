"""Estimate center durations and independently verify calibrated upper durations."""

from dataclasses import dataclass
from math import ceil

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from .work_order import ACCESS_TYPES, FIXTURES, HARDNESS_BANDS


COVERAGE = 0.90
MIN_TRAIN, MIN_CALIBRATION, MIN_AUDIT = 40, 20, 15
COHORT_HINT = f"请准备至少 {MIN_TRAIN} 条训练、{MIN_CALIBRATION} 条校准及 {MIN_AUDIT} 条独立核验工单。"


def check_cohorts(history: list[dict], calibration: list[dict], audit: list[dict]) -> None:
    if len(history) < MIN_TRAIN or len(calibration) < MIN_CALIBRATION or len(audit) < MIN_AUDIT:
        raise ValueError(COHORT_HINT)


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
    audit_mae: float = 0.0
    audit_upper_covered: int = 0
    audit_count: int = 0

    @classmethod
    def train(cls, history: list[dict], calibration: list[dict], audit: list[dict]) -> "DurationFit":
        check_cohorts(history, calibration, audit)
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

        fit = cls(estimator, buffer)
        mae, exceeded, count = fit.assess(audit)
        return cls(estimator, buffer, mae, count - exceeded, count)

    @staticmethod
    def predict(estimator: HistGradientBoostingRegressor, rows: list[dict]) -> np.ndarray:
        return np.maximum(1, estimator.predict(_inputs(rows)))

    @property
    def audit_exceeded(self) -> int:
        return self.audit_count - self.audit_upper_covered

    def assess(self, rows: list[dict]) -> tuple[float, int, int]:
        """Score held-out completion records without using them for training or calibration."""
        actual = _minutes(rows)
        center = self.predict(self.model, rows)
        mae = float(np.abs(actual - center).mean())
        exceeded = int((actual > np.ceil(center + self.buffer)).sum())
        return mae, exceeded, len(rows)

    def forecasts(self, rows: list[dict]) -> list[tuple[float, int]]:
        estimates = self.predict(self.model, rows)
        return [(round(float(estimate), 1), ceil(float(estimate) + self.buffer)) for estimate in estimates]
