"""Configurable fictional unit-economics calculations."""

from __future__ import annotations

import pandas as pd


def expected_incremental_value(
    churn_probability: pd.Series,
    response_probability: pd.Series,
    customer_value: pd.Series,
    *,
    treatment_effect_if_response: float,
    contact_cost: float,
    incentive_cost: float = 0.0,
) -> pd.Series:
    """Expected net value per customer under a configurable intervention scenario.

    The benefit is ``P(churn) * P(response) * treatment_effect_if_response * value``.
    This is an economic assumption, not a causal estimate by itself.
    """
    inputs = pd.DataFrame(
        {"churn": churn_probability, "response": response_probability, "value": customer_value}
    )
    if (
        inputs.isna().any().any()
        or (inputs[["churn", "response"]] < 0).any().any()
        or (inputs[["churn", "response"]] > 1).any().any()
    ):
        raise ValueError("probabilities must be present and in [0, 1]")
    if (
        (inputs["value"] < 0).any()
        or treatment_effect_if_response < 0
        or contact_cost < 0
        or incentive_cost < 0
    ):
        raise ValueError("values, effect, and costs must be non-negative")
    return (
        inputs["churn"] * inputs["response"] * treatment_effect_if_response * inputs["value"]
        - contact_cost
        - incentive_cost
    ).rename("expected_net_value")


def target_customers(
    frame: pd.DataFrame,
    *,
    churn_col: str,
    response_col: str,
    value_col: str,
    treatment_effect_if_response: float,
    contact_cost: float,
    incentive_cost: float = 0.0,
    capacity: int | None = None,
) -> pd.DataFrame:
    """Rank positive-value customers and optionally enforce contact capacity."""
    required = {churn_col, response_col, value_col}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    output = frame.copy()
    output["expected_net_value"] = expected_incremental_value(
        output[churn_col],
        output[response_col],
        output[value_col],
        treatment_effect_if_response=treatment_effect_if_response,
        contact_cost=contact_cost,
        incentive_cost=incentive_cost,
    )
    selected = output[output["expected_net_value"] > 0].sort_values(
        "expected_net_value", ascending=False
    )
    if capacity is not None:
        if capacity < 0:
            raise ValueError("capacity must be non-negative")
        selected = selected.head(capacity)
    selected["target_rank"] = range(1, len(selected) + 1)
    return selected


def strategy_comparison(
    frame: pd.DataFrame,
    *,
    churn_col: str,
    response_col: str,
    value_col: str,
    treatment_effect_if_response: float,
    contact_cost: float,
    incentive_cost: float = 0.0,
    capacity_fraction: float = 0.1,
) -> pd.DataFrame:
    """Compare contact-all, single-score, and expected-value targeting under one scenario."""
    if not 0 < capacity_fraction <= 1:
        raise ValueError("capacity_fraction must be in (0, 1]")
    output = frame.copy()
    output["expected_net_value"] = expected_incremental_value(
        output[churn_col],
        output[response_col],
        output[value_col],
        treatment_effect_if_response=treatment_effect_if_response,
        contact_cost=contact_cost,
        incentive_cost=incentive_cost,
    )
    capacity = max(1, int(len(output) * capacity_fraction))
    selections = {
        "contact_all": output,
        "risk": output.nlargest(capacity, churn_col),
        "value": output.nlargest(capacity, value_col),
        "response": output.nlargest(capacity, response_col),
        "expected_value": output.loc[output["expected_net_value"] > 0].nlargest(
            capacity, "expected_net_value"
        ),
    }
    return pd.DataFrame(
        [
            {
                "strategy": name,
                "customers_contacted": len(selected),
                "contact_rate": len(selected) / len(output),
                "expected_net_value": selected["expected_net_value"].sum(),
                "expected_net_value_per_contact": selected["expected_net_value"].mean()
                if len(selected)
                else 0.0,
                "profitable": bool(selected["expected_net_value"].sum() > 0),
            }
            for name, selected in selections.items()
        ]
    )


def economics_sensitivity(frame: pd.DataFrame, **kwargs: object) -> pd.DataFrame:
    """Sensitivity of the expected-value strategy to transparent effect/cost assumptions."""
    rows = []
    base_effect = float(kwargs.pop("treatment_effect_if_response"))
    base_cost = float(kwargs.pop("contact_cost"))
    for effect_multiplier in (0.5, 1.0, 1.5):
        for cost_multiplier in (0.5, 1.0, 1.5):
            comparison = strategy_comparison(
                frame,
                **kwargs,
                treatment_effect_if_response=base_effect * effect_multiplier,
                contact_cost=base_cost * cost_multiplier,
            )
            row = comparison.loc[comparison["strategy"].eq("expected_value")].iloc[0].to_dict()
            row.update(
                {"effect_multiplier": effect_multiplier, "contact_cost_multiplier": cost_multiplier}
            )
            rows.append(row)
    return pd.DataFrame(rows)
