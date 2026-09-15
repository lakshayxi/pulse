"""Simple distribution and performance stability diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pulse.models.evaluation import model_metrics


def population_stability_index(
    reference: pd.Series, current: pd.Series, *, bins: int = 10
) -> float:
    """Calculate PSI using reference quantile bins with finite clipping."""
    ref, cur = reference.dropna().to_numpy(float), current.dropna().to_numpy(float)
    if len(ref) == 0 or len(cur) == 0:
        return float("nan")
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 2:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    expected = np.histogram(ref, bins=edges)[0] / len(ref)
    actual = np.histogram(cur, bins=edges)[0] / len(cur)
    expected, actual = np.clip(expected, 1e-6, None), np.clip(actual, 1e-6, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def stability_report(
    train: pd.DataFrame,
    test: pd.DataFrame,
    probabilities: pd.Series,
    target: pd.Series,
    features: list[str],
) -> pd.DataFrame:
    metrics = model_metrics(target, probabilities)
    rows = [
        {
            "kind": "performance",
            "measure": name,
            "value": value,
            "interpretation": "later temporal holdout",
        }
        for name, value in metrics.items()
    ]
    for feature in features:
        if pd.api.types.is_numeric_dtype(train[feature]):
            psi = population_stability_index(train[feature], test[feature])
            rows.append(
                {
                    "kind": "feature_drift",
                    "measure": feature,
                    "value": psi,
                    "interpretation": "PSI: <0.1 low, 0.1-0.25 moderate, >0.25 material",
                }
            )
    return pd.DataFrame(rows)


def performance_over_time(
    test_frame: pd.DataFrame,
    probabilities: pd.Series,
    target: pd.Series,
    *,
    time_col: str = "feature_cutoff",
    frequency: str = "M",
) -> pd.DataFrame:
    """Evaluate the temporal holdout in deterministic time buckets.

    This is descriptive monitoring evidence: each bucket is scored with the
    already-fitted model and does not imply a causal or prospective estimate.
    "MS" gives calendar-month buckets while remaining deterministic for the
    synthetic date range.
    """
    if time_col not in test_frame:
        raise ValueError(f"test_frame must contain {time_col!r}")
    if len(test_frame) != len(probabilities) or len(test_frame) != len(target):
        raise ValueError("test_frame, probabilities, and target must have equal length")
    data = pd.DataFrame(
        {
            "time_bucket": pd.to_datetime(test_frame[time_col])
            .dt.to_period(frequency)
            .dt.start_time,
            "target": target.to_numpy(dtype=int),
            "probability": probabilities.to_numpy(dtype=float),
        }
    )
    rows: list[dict[str, float | int | str]] = []
    for bucket, group in data.groupby("time_bucket", sort=True):
        metrics = model_metrics(group["target"], group["probability"])
        base_rate = float(group["target"].mean())
        mean_predicted = float(group["probability"].mean())
        rows.append(
            {
                "time_bucket": bucket.strftime("%Y-%m-%d"),
                "customers": len(group),
                "base_rate": base_rate,
                "mean_predicted": mean_predicted,
                "calibration_error": abs(mean_predicted - base_rate),
                **metrics,
            }
        )
    return pd.DataFrame(rows)
