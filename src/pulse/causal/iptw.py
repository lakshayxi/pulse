"""Stabilized IPTW construction and overlap/balance diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd


def stabilized_iptw_weights(
    treatment: pd.Series, propensity: pd.Series, *, clip: tuple[float, float] | None = (0.01, 0.99)
) -> pd.Series:
    """Build marginally stabilized binary-treatment weights from pre-treatment propensities."""
    joined = pd.DataFrame({"treatment": treatment, "propensity": propensity})
    if joined.isna().any().any():
        raise ValueError("treatment and propensity cannot contain missing values")
    if not joined["treatment"].isin([0, 1, False, True]).all():
        raise ValueError("treatment must be binary")
    if not ((joined["propensity"] > 0) & (joined["propensity"] < 1)).all():
        raise ValueError("propensity values must lie strictly between 0 and 1")
    if clip is not None:
        lower, upper = clip
        if not 0 < lower < upper < 1:
            raise ValueError("clip bounds must satisfy 0 < lower < upper < 1")
        propensity = propensity.clip(lower, upper)
    treated_share = treatment.astype(float).mean()
    weights = pd.Series(
        np.where(
            treatment.astype(bool),
            treated_share / propensity,
            (1 - treated_share) / (1 - propensity),
        ),
        index=treatment.index,
        name="stabilized_iptw",
    )
    return weights


def effective_sample_size(weights: pd.Series) -> float:
    """Return Kish effective sample size for non-negative finite weights."""
    values = weights.to_numpy(dtype=float)
    if len(values) == 0 or not np.isfinite(values).all() or (values < 0).any() or values.sum() == 0:
        raise ValueError("weights must be finite, non-negative, and sum to a positive value")
    return float(values.sum() ** 2 / np.square(values).sum())


def balance_table(
    frame: pd.DataFrame, *, treatment_col: str, covariates: list[str], weight_col: str | None = None
) -> pd.DataFrame:
    """Compare treated/control covariate means using unweighted or weighted SMDs."""
    if treatment_col not in frame or not set(covariates).issubset(frame.columns):
        raise ValueError("treatment and all covariates must exist")
    if weight_col is not None and weight_col not in frame:
        raise ValueError("weight_col must exist")
    rows: list[dict[str, float | str]] = []
    for covariate in covariates:
        data = frame[[treatment_col, covariate] + ([weight_col] if weight_col else [])].dropna()
        treated, control = (
            data[data[treatment_col].astype(bool)],
            data[~data[treatment_col].astype(bool)],
        )
        if treated.empty or control.empty:
            raise ValueError("both treatment groups require observations")
        if weight_col:
            wt, wc = treated[weight_col].to_numpy(float), control[weight_col].to_numpy(float)
            mt, mc = (
                np.average(treated[covariate], weights=wt),
                np.average(control[covariate], weights=wc),
            )
            vt = np.average((treated[covariate] - mt) ** 2, weights=wt)
            vc = np.average((control[covariate] - mc) ** 2, weights=wc)
        else:
            mt, mc = treated[covariate].mean(), control[covariate].mean()
            vt, vc = treated[covariate].var(ddof=1), control[covariate].var(ddof=1)
        denominator = np.sqrt((vt + vc) / 2)
        rows.append(
            {
                "covariate": covariate,
                "treated_mean": float(mt),
                "control_mean": float(mc),
                "standardized_mean_difference": float((mt - mc) / denominator)
                if denominator
                else 0.0,
            }
        )
    return pd.DataFrame(rows)
