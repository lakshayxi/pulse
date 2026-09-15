import pandas as pd

from pulse.analytics.analysis import retention_cohorts


def test_retention_uses_exact_inclusive_windows_and_excludes_immature_cohorts() -> None:
    customers = pd.DataFrame(
        {
            "customer_id": [1, 2],
            "signup_date": ["2025-01-01", "2025-03-01"],
            "acquisition_channel": ["organic", "organic"],
        }
    )
    transactions = pd.DataFrame(
        {
            "customer_id": [1, 1, 1, 1, 2],
            "transaction_id": ["a", "b", "c", "d", "e"],
            "timestamp": ["2025-01-08", "2025-01-14", "2025-01-31", "2025-04-20", "2025-03-08"],
            "status": ["settled"] * 5,
        }
    )
    result = retention_cohorts(customers, transactions)
    d7 = result.loc[(result["cohort_month"] == "2025-01") & result["horizon_days"].eq(7)].iloc[0]
    d30 = result.loc[(result["cohort_month"] == "2025-01") & result["horizon_days"].eq(30)].iloc[0]
    assert d7["retention"] == 1.0  # Day 7 is included; day 13 is the window end.
    assert d30["retention"] == 1.0  # Day 30 is included.
    assert result.loc[result["cohort_month"].eq("2025-03"), "horizon_days"].max() == 30
