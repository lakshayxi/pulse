import pandas as pd
import pytest

from pulse.features.temporal import build_churn_snapshots, validate_snapshot_leakage


def test_snapshots_exclude_future_transactions() -> None:
    customers = pd.DataFrame(
        {
            "customer_id": [1],
            "signup_date": ["2025-01-01"],
            "acquisition_channel": ["organic"],
            "initial_segment": ["starter"],
        }
    )
    transactions = pd.DataFrame(
        {
            "transaction_id": ["pre", "future"],
            "customer_id": [1, 1],
            "timestamp": ["2025-01-10", "2025-02-15"],
            "status": ["settled", "settled"],
            "amount": [10.0, 999.0],
            "merchant_category": ["bills", "retail"],
        }
    )
    holdings = pd.DataFrame(columns=["customer_id", "product_type", "opened_at"])
    events = pd.DataFrame(columns=["customer_id", "event_type", "event_timestamp"])
    snapshot = build_churn_snapshots(customers, transactions, holdings, events)
    assert snapshot.loc[0, "tx_count_30d"] == 1
    assert snapshot.loc[0, "gross_volume_30d"] == 10.0
    assert snapshot.loc[0, "churned"] == 0


def test_leakage_validator_rejects_target_field() -> None:
    with pytest.raises(ValueError, match="target"):
        validate_snapshot_leakage(pd.DataFrame({"feature_cutoff": ["2025-01-01"], "churned": [0]}))


def test_leakage_validator_rejects_future_feature_timestamp() -> None:
    frame = pd.DataFrame({"feature_cutoff": ["2025-01-01"], "tx_count_30d": [1]})
    with pytest.raises(ValueError, match="future"):
        validate_snapshot_leakage(frame, pd.Series(["2025-01-02"]))
