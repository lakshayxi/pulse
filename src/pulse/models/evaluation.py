"""Reusable ranking and probability evaluation metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


def ranking_table(
    y_true: pd.Series, probabilities: pd.Series, *, fractions: tuple[float, ...] = (0.1, 0.2, 0.3)
) -> pd.DataFrame:
    data = pd.DataFrame(
        {"target": y_true.astype(int), "score": probabilities.astype(float)}
    ).sort_values("score", ascending=False)
    total_events = data["target"].sum()
    rows = []
    for fraction in fractions:
        count = max(1, int(np.ceil(len(data) * fraction)))
        selected = data.head(count)
        rate = selected["target"].mean()
        base = data["target"].mean()
        rows.append(
            {
                "target_fraction": fraction,
                "customers": count,
                "event_rate": rate,
                "precision": rate,
                "capture": selected["target"].sum() / total_events if total_events else 0.0,
                "lift": rate / base if base else 0.0,
            }
        )
    return pd.DataFrame(rows)


def model_metrics(y_true: pd.Series, probabilities: pd.Series) -> dict[str, float | int]:
    y = y_true.astype(int)
    p = probabilities.clip(1e-6, 1 - 1e-6)
    metrics = {"brier": float(brier_score_loss(y, p))}
    metrics["roc_auc"] = float(roc_auc_score(y, p)) if y.nunique() == 2 else float("nan")
    metrics["pr_auc"] = float(average_precision_score(y, p)) if y.nunique() == 2 else float("nan")
    top = ranking_table(y, p).iloc[0]
    metrics.update(
        {
            "evaluation_customers": len(y),
            "evaluation_events": int(y.sum()),
            "top_decile_customers": int(top.customers),
            "lift_at_10pct": float(top.lift),
            "capture_at_10pct": float(top.capture),
            "precision_at_10pct": float(top.precision),
        }
    )
    return metrics


def calibration_table(
    y_true: pd.Series, probabilities: pd.Series, *, bins: int = 10
) -> pd.DataFrame:
    data = pd.DataFrame({"target": y_true, "probability": probabilities.clip(0, 1)})
    data["bin"] = pd.cut(data["probability"], bins=np.linspace(0, 1, bins + 1), include_lowest=True)
    return (
        data.groupby("bin", observed=True)
        .agg(
            predicted_rate=("probability", "mean"),
            observed_rate=("target", "mean"),
            customers=("target", "size"),
        )
        .reset_index()
    )
