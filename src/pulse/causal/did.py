"""Difference-in-differences calculations with explicit panel contracts."""

from __future__ import annotations

import pandas as pd


def difference_in_differences(
    frame: pd.DataFrame,
    *,
    group_col: str,
    post_col: str,
    outcome_col: str,
    treated_value: object = 1,
) -> dict[str, float]:
    """Estimate the 2x2 DiD contrast: treated change minus control change.

    ``post_col`` must be a binary period indicator and inputs must contain all
    four group-period cells. This estimator does not establish parallel trends.
    """
    required = {group_col, post_col, outcome_col}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    data = frame.loc[:, list(required)].dropna()
    if data.empty:
        raise ValueError("no complete rows available")
    means = data.groupby([group_col, post_col], observed=True)[outcome_col].mean()
    treated = treated_value
    controls = [value for value in data[group_col].unique() if value != treated]
    if len(controls) != 1:
        raise ValueError("group_col must contain exactly one treated and one control group")
    control = controls[0]
    try:
        treated_pre, treated_post = means[(treated, 0)], means[(treated, 1)]
        control_pre, control_post = means[(control, 0)], means[(control, 1)]
    except KeyError as error:
        raise ValueError("all treated/control and pre/post cells are required") from error
    treated_change, control_change = treated_post - treated_pre, control_post - control_pre
    return {
        "treated_pre": float(treated_pre),
        "treated_post": float(treated_post),
        "control_pre": float(control_pre),
        "control_post": float(control_post),
        "treated_change": float(treated_change),
        "control_change": float(control_change),
        "did_effect": float(treated_change - control_change),
    }


def parallel_trend_summary(
    frame: pd.DataFrame,
    *,
    period_col: str,
    group_col: str,
    outcome_col: str,
    treated_value: object = 1,
) -> pd.DataFrame:
    """Produce pre/post group means and treated-minus-control gaps for trend review."""
    required = {period_col, group_col, outcome_col}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    pivot = frame.pivot_table(
        index=period_col, columns=group_col, values=outcome_col, aggfunc="mean"
    )
    controls = [value for value in pivot.columns if value != treated_value]
    if treated_value not in pivot.columns or len(controls) != 1:
        raise ValueError("need exactly one treated and one control group")
    result = pivot.rename(columns={treated_value: "treated", controls[0]: "control"}).reset_index()
    result["treated_minus_control"] = result["treated"] - result["control"]
    return result
