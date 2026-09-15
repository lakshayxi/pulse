"""Leakage-safe customer snapshots for temporal prediction tasks."""

from __future__ import annotations

import pandas as pd

FEATURE_COLUMNS = [
    "tx_count_30d",
    "active_days_30d",
    "gross_volume_30d",
    "category_breadth_30d",
    "days_since_last_tx",
    "has_savings",
    "funded_by_cutoff",
]


def build_churn_snapshots(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    holdings: pd.DataFrame,
    events: pd.DataFrame,
    *,
    observation_days: int = 30,
    horizon_days: int = 30,
) -> pd.DataFrame:
    """Build one row per customer using only data on/before a customer cutoff.

    Customers must be active in the observation window. ``churned`` means no
    settled transaction in the strictly future prediction window.
    """
    if observation_days <= 0 or horizon_days <= 0:
        raise ValueError("observation_days and horizon_days must be positive")
    base = customers[
        ["customer_id", "signup_date", "acquisition_channel", "initial_segment"]
    ].copy()
    base["signup_date"] = pd.to_datetime(base["signup_date"])
    base["feature_cutoff"] = base["signup_date"] + pd.Timedelta(days=observation_days)
    tx = transactions.loc[transactions["status"].eq("settled")].copy()
    tx["timestamp"] = pd.to_datetime(tx["timestamp"])
    joined = tx.merge(
        base[["customer_id", "signup_date", "feature_cutoff"]], on="customer_id", how="inner"
    )
    observed = joined[
        (joined["timestamp"] >= joined["signup_date"])
        & (joined["timestamp"] <= joined["feature_cutoff"])
    ]
    summary = observed.groupby("customer_id", as_index=False).agg(
        tx_count_30d=("transaction_id", "nunique"),
        active_days_30d=("timestamp", lambda x: x.dt.date.nunique()),
        gross_volume_30d=("amount", "sum"),
        category_breadth_30d=("merchant_category", "nunique"),
        last_tx_at=("timestamp", "max"),
    )
    snapshots = base.merge(summary, on="customer_id", how="left")
    snapshots = snapshots[snapshots["tx_count_30d"].notna()].copy()
    snapshots["days_since_last_tx"] = (
        snapshots["feature_cutoff"] - snapshots.pop("last_tx_at")
    ).dt.days
    snapshots[["tx_count_30d", "active_days_30d", "gross_volume_30d", "category_breadth_30d"]] = (
        snapshots[
            ["tx_count_30d", "active_days_30d", "gross_volume_30d", "category_breadth_30d"]
        ].fillna(0)
    )
    hold = holdings.copy()
    hold["opened_at"] = pd.to_datetime(hold["opened_at"])
    savings = (
        hold.loc[hold["product_type"].eq("savings")]
        .groupby("customer_id", as_index=False)["opened_at"]
        .min()
    )
    snapshots = snapshots.merge(
        savings.rename(columns={"opened_at": "savings_opened_at"}), on="customer_id", how="left"
    )
    snapshots["has_savings"] = (
        (snapshots["savings_opened_at"] <= snapshots["feature_cutoff"]).fillna(False).astype(int)
    )
    snapshots = snapshots.drop(columns="savings_opened_at")
    funded = events.loc[
        events["event_type"].eq("account_funded"), ["customer_id", "event_timestamp"]
    ].copy()
    funded["event_timestamp"] = pd.to_datetime(funded["event_timestamp"])
    funded = funded.groupby("customer_id", as_index=False)["event_timestamp"].min()
    snapshots = snapshots.merge(
        funded.rename(columns={"event_timestamp": "funded_at"}), on="customer_id", how="left"
    )
    snapshots["funded_by_cutoff"] = (
        (snapshots["funded_at"] <= snapshots["feature_cutoff"]).fillna(False).astype(int)
    )
    snapshots = snapshots.drop(columns="funded_at")
    future = joined[
        (joined["timestamp"] > joined["feature_cutoff"])
        & (joined["timestamp"] <= joined["feature_cutoff"] + pd.Timedelta(days=horizon_days))
    ]
    active_future = set(future["customer_id"])
    snapshots["churned"] = (~snapshots["customer_id"].isin(active_future)).astype(int)
    snapshots["prediction_end"] = snapshots["feature_cutoff"] + pd.Timedelta(days=horizon_days)
    return snapshots.sort_values(["feature_cutoff", "customer_id"]).reset_index(drop=True)


def validate_snapshot_leakage(
    frame: pd.DataFrame, feature_timestamps: pd.Series | None = None
) -> None:
    """Raise when target fields or future event timestamps are in a feature set."""
    forbidden = {"churned", "prediction_end", "d30_active", "first_week_activation"}
    overlap = forbidden.intersection(frame.columns)
    if overlap:
        raise ValueError(f"target/post-outcome columns cannot be model features: {sorted(overlap)}")
    if (
        feature_timestamps is not None
        and (pd.to_datetime(feature_timestamps) > pd.to_datetime(frame["feature_cutoff"])).any()
    ):
        raise ValueError("future event timestamp found in feature data")
