import pandas as pd

from pulse.analytics.analysis import journey_analysis, retention_cohorts
from pulse.simulation import generate_dataset
from pulse.simulation.generator import write_dataset
from pulse.warehouse import build_warehouse, run_models


def _boundary_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    customers = pd.DataFrame(
        {
            "customer_id": [1, 2, 3, 4],
            "signup_date": pd.to_datetime(["2025-01-01"] * 4),
            "acquisition_channel": "organic",
            "age_band": "30-44",
            "region_group": "north",
            "initial_segment": "everyday",
            "onboarding_completed": True,
            "account_funded": [True, True, True, False],
        }
    )
    events = pd.DataFrame(
        [
            ("e1", 1, "2025-01-02", "account_funded"),
            ("e2", 2, "2025-01-02", "account_funded"),
            ("e3", 3, "2025-01-02", "account_funded"),
        ],
        columns=["event_id", "customer_id", "event_timestamp", "event_type"],
    )
    events["event_timestamp"] = pd.to_datetime(events["event_timestamp"])
    transactions = pd.DataFrame(
        [
            ("t1", 1, "2025-01-08 23:59", "card_transaction", "retail", 10, "settled", "app"),
            ("t2", 1, "2025-02-06 23:59", "transfer", "retail", 10, "settled", "app"),
            ("t3", 2, "2025-01-09 00:00", "card_transaction", "retail", 10, "settled", "app"),
            ("t4", 2, "2025-02-06 00:00", "bill_payment", "retail", 10, "settled", "app"),
            ("t5", 3, "2025-01-08 00:00", "cash_withdrawal", "retail", 10, "settled", "app"),
            ("t6", 4, "2025-01-08 00:00", "card_transaction", "retail", 10, "settled", "app"),
            ("t7", 1, "2025-01-08 00:00", "card_transaction", "retail", 10, "failed", "app"),
        ],
        columns=[
            "transaction_id",
            "customer_id",
            "timestamp",
            "transaction_type",
            "merchant_category",
            "amount",
            "status",
            "channel",
        ],
    )
    transactions["timestamp"] = pd.to_datetime(transactions["timestamp"])
    return customers, events, transactions


def test_activation_and_d30_windows_are_inclusive_and_exclude_invalid_transactions():
    customers, events, transactions = _boundary_tables()
    journey = journey_analysis(customers, events, transactions).set_index("stage")
    assert journey.loc["first_transaction_7d", "customers"] == 1
    assert journey.loc["sustained_engagement_d30", "customers"] == 1
    assert journey.loc["d30_retention_overall", "customers"] == 2


def test_python_and_sql_activation_funnel_counts_agree(tmp_path):
    tables = generate_dataset(250, seed=19)
    write_dataset(tables, tmp_path)
    con = build_warehouse(tmp_path)
    try:
        run_models(con)
        journey = journey_analysis(
            tables["customers"], tables["customer_events"], tables["transactions"]
        ).set_index("stage")
        sql = con.execute("SELECT * FROM customer_activation").fetchdf()
        assert int(sql["activated"].sum()) == int(journey.loc["first_transaction_7d", "customers"])
        assert int(sql["d30_active"].sum()) == int(
            journey.loc["d30_retention_overall", "customers"]
        )
        assert int(sql["settled_meaningful_transaction_count"].sum()) == int(
            tables["transactions"]
            .query(
                "status == 'settled' and transaction_type in ['card_transaction', 'transfer', 'bill_payment']"
            )
            .transaction_id.nunique()
        )
    finally:
        con.close()


def test_retention_windows_use_inclusive_calendar_days_and_meaningful_types():
    customers = pd.DataFrame(
        {
            "customer_id": [1, 2],
            "signup_date": pd.to_datetime(["2025-01-01", "2025-01-01"]),
            "acquisition_channel": ["organic", "organic"],
        }
    )
    transactions = pd.DataFrame(
        [
            ("t1", 1, "2025-01-08 23:59", "card_transaction", "settled"),  # D7
            ("t2", 1, "2025-02-06 23:59", "transfer", "settled"),  # D36
            ("t3", 1, "2025-03-08 23:59", "bill_payment", "settled"),  # D66
            ("t4", 1, "2025-04-07 23:59", "card_transaction", "settled"),  # D96
            ("t5", 2, "2025-01-15 23:59", "cash_withdrawal", "settled"),  # outside D7
            ("t6", 2, "2025-01-08 23:59", "card_transaction", "failed"),  # excluded status
        ],
        columns=["transaction_id", "customer_id", "timestamp", "transaction_type", "status"],
    )
    output = retention_cohorts(customers, transactions)
    output = output.sort_values("horizon_days").reset_index(drop=True)
    assert output["horizon_days"].tolist() == [7, 30, 60, 90]
    assert output["window_end_day"].tolist() == [13, 36, 66, 96]
    assert output["retention"].tolist() == [0.5, 0.5, 0.5, 0.5]
