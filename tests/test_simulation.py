import pandas as pd

from pulse.analytics.analysis import (
    journey_analysis,
    retention_cohorts,
    selected_region_campaign_analysis,
)
from pulse.simulation import generate_dataset


def test_generation_is_deterministic():
    a, b = generate_dataset(80), generate_dataset(80)
    for name in a:
        pd.testing.assert_frame_equal(a[name], b[name])


def test_retention_lifecycle_is_monotonic_on_fixed_large_sample():
    tables = generate_dataset(12_000, seed=1729)
    retention = retention_cohorts(tables["customers"], tables["transactions"])
    means = (
        retention.groupby("horizon_days")
        .apply(
            lambda frame: (
                (frame["retention"] * frame["cohort_size"]).sum() / frame["cohort_size"].sum()
            ),
            include_groups=False,
        )
        .sort_index()
    )

    assert means.index.tolist() == [7, 30, 60, 90]
    assert means.between(0.0, 1.0).all()
    assert means.diff().dropna().lt(0).all()


def test_late_activation_separates_overall_and_sustained_d30():
    tables = generate_dataset(12_000, seed=1729)
    outcomes = tables["experiment_outcomes"]
    assert outcomes["d30_active"].mean() > outcomes["d30_sustained_engagement"].mean()


def test_cohort_shapes_are_not_identical_rescaled_copies():
    tables = generate_dataset(18_000, seed=1729)
    retention = retention_cohorts(tables["customers"], tables["transactions"])
    matrix = retention.pivot(index="cohort_month", columns="horizon_days", values="retention")
    shapes = matrix.div(matrix[7], axis=0)
    assert shapes.round(4).drop_duplicates().shape[0] >= 4
    assert matrix[30].rank(method="min").equals(matrix[60].rank(method="min")) is False


def test_reactivation_can_create_local_cohort_pulse_without_breaking_aggregate_decline():
    tables = generate_dataset(30_000, seed=1729)
    retention = retention_cohorts(tables["customers"], tables["transactions"])
    matrix = retention.pivot(index="cohort_month", columns="horizon_days", values="retention")
    aggregate = matrix.mean()

    assert ((matrix[60] > matrix[30]) | (matrix[90] > matrix[60])).any()
    assert aggregate[7] > aggregate[30] > aggregate[60] > aggregate[90]


def test_fake_ids_and_observed_ground_truth_boundary():
    tables = generate_dataset(100)
    assert tables["customers"].customer_id.is_unique
    assert not any("quality" in c for c in tables["customers"].columns)
    assert tables["transactions"].amount.ge(0).all()


def test_activation_inputs_are_observable_and_bounded():
    tables = generate_dataset(400)
    customers = tables["customers"].set_index("customer_id")
    settled = tables["transactions"].query("status == 'settled'")
    meaningful = settled[
        settled.transaction_type.isin(["card_transaction", "transfer", "bill_payment"])
    ]
    first = meaningful.groupby("customer_id").timestamp.min()
    # Every settled first transaction is in the generated 120-day horizon; the
    # canonical activation mart applies the stricter seven-day window.
    assert (first - customers.loc[first.index, "signup_date"]).dt.days.ge(0).all()
    assert tables["transactions"].status.isin(["settled", "failed"]).all()


def test_rct_timing_and_outcomes_follow_calendar_day_activation_contract():
    tables = generate_dataset(800)
    eligible = tables["experiment_assignments"].query("eligible")
    transactions = tables["transactions"].merge(
        eligible[["customer_id", "assignment_date"]], on="customer_id", how="inner"
    )
    assert (transactions["timestamp"] >= transactions["assignment_date"]).all()
    customers = tables["customers"].set_index("customer_id")
    settled = tables["transactions"].query("status == 'settled'").copy()
    settled["day"] = (
        settled["timestamp"].dt.normalize()
        - customers.loc[settled["customer_id"], "signup_date"].to_numpy()
    ).dt.days
    activated = set(
        settled.loc[
            settled["transaction_type"].isin(["card_transaction", "transfer", "bill_payment"])
            & settled["day"].between(0, 7),
            "customer_id",
        ]
    )
    expected = tables["customers"].account_funded & tables["customers"].customer_id.isin(activated)
    assert tables["experiment_outcomes"]["first_week_activation"].tolist() == expected.tolist()


def test_journey_is_sequential_and_campaign_is_not_deterministic_by_region():
    tables = generate_dataset(1_000)
    journey = journey_analysis(
        tables["customers"], tables["customer_events"], tables["transactions"]
    )
    sequential = journey.query("metric_scope == 'sequential_funnel'")["customers"]
    assert sequential.is_monotonic_decreasing
    assert (
        journey.query("stage == 'd30_retention_overall'")["metric_scope"].item()
        == "overall_retention"
    )
    campaign = tables["campaign_assignments"].query("eligible")
    assert campaign.groupby("region_group")["selected_region"].nunique().eq(2).all()
    output = selected_region_campaign_analysis(
        tables["customers"], tables["transactions"], tables["campaign_assignments"]
    )
    assert {"unweighted", "stabilized_iptw"} == set(output["balance"]["weighting"])
    assert "iptw_ci_high" in output["iptw_effect"]
