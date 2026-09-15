"""Deterministic synthetic digital-banking event generator."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import ground_truth

_CHANNELS = np.array(["organic", "referral", "paid", "partner"])
_SEGMENTS = np.array(["everyday", "builder", "starter"])
_TYPES = np.array(["card_transaction", "transfer", "bill_payment"])
_CATEGORIES = np.array(["groceries", "transport", "bills", "retail", "dining"])


def _cohort_seasonality(signup_date: pd.Timestamp) -> float:
    """Return a small, deterministic engagement multiplier for a signup cohort."""
    month_phase = 2 * np.pi * (signup_date.month - 1) / 12
    return 1.0 + ground_truth.COHORT_SEASONALITY_AMPLITUDE * np.sin(month_phase - 0.65)


def _cohort_operational_shock(signup_date: pd.Timestamp) -> float:
    """Return a synthetic period shock for acquisition and early operations."""
    month_index = (signup_date.year - 2025) * 12 + signup_date.month - 1
    return ground_truth.COHORT_OPERATIONAL_SHOCKS[
        month_index % len(ground_truth.COHORT_OPERATIONAL_SHOCKS)
    ]


def _cohort_reactivation_shock(signup_date: pd.Timestamp) -> float:
    """Return a synthetic later-life-cycle shock by signup period."""
    month_index = (signup_date.year - 2025) * 12 + signup_date.month - 1
    return ground_truth.COHORT_REACTIVATION_SHOCKS[
        month_index % len(ground_truth.COHORT_REACTIVATION_SHOCKS)
    ]


def generate_dataset(n_customers: int = 2_000, seed: int = 1729) -> dict[str, pd.DataFrame]:
    """Return observed synthetic tables. Same inputs always produce identical rows."""
    rng = np.random.default_rng(seed)
    ids = np.arange(1, n_customers + 1)
    signup = pd.Timestamp("2025-01-01") + pd.to_timedelta(
        rng.integers(0, 270, n_customers), unit="D"
    )
    channel = rng.choice(_CHANNELS, n_customers, p=[0.38, 0.18, 0.29, 0.15])
    segment = rng.choice(_SEGMENTS, n_customers, p=[0.45, 0.30, 0.25])
    quality = np.array([ground_truth.CHANNEL_QUALITY[c] for c in channel])
    quality += np.array([ground_truth.SEGMENT_ENGAGEMENT[s] for s in segment]) * 0.25
    onboard = rng.random(n_customers) < np.clip(quality, 0.08, 0.95)
    funded = onboard & (rng.random(n_customers) < 0.78)
    # The intervention is only offered to funded customers who have not yet
    # completed the meaningful first-transaction step at assignment time.
    eligible = funded & (rng.random(n_customers) < 0.64)
    assignment = np.where(
        eligible, np.where(rng.random(n_customers) < 0.5, "control", "treatment"), None
    )
    # A distinct observational campaign has region-influenced, but not
    # deterministic, assignment. This preserves overlap for its explicitly
    # observational analysis while retaining geographic confounding.
    campaign_region = "north"
    comparison_region = "south"
    customers_region = rng.choice(["north", "south", "west", "east"], n_customers)
    campaign_eligible = np.isin(customers_region, [campaign_region, comparison_region])
    region_log_odds = np.where(customers_region == campaign_region, 0.85, -0.85)
    campaign_probability = 1 / (1 + np.exp(-(region_log_odds + 0.45 * quality)))
    campaign_treated = campaign_eligible & (rng.random(n_customers) < campaign_probability)
    first_tx = funded & (
        rng.random(n_customers)
        < np.clip(
            0.28 + quality * 0.55 + (assignment == "treatment") * ground_truth.TREATMENT_LIFT,
            0,
            0.98,
        )
    )
    # Latent product depth is a customer-level propensity for multi-product
    # adoption and repeat use. It is deliberately not exposed as a feature.
    product_depth = np.clip(
        0.42 + quality * 0.42 + rng.normal(0.0, ground_truth.PRODUCT_DEPTH_NOISE_SD, n_customers),
        0.08,
        1.20,
    )
    late_activation = (
        funded
        & ~first_tx
        & (
            rng.random(n_customers)
            < np.clip(
                ground_truth.LATE_ACTIVATION_BASE_RATE
                + ground_truth.LATE_ACTIVATION_QUALITY_RATE * quality,
                0.05,
                0.42,
            )
        )
    )
    customers = pd.DataFrame(
        {
            "customer_id": ids,
            "signup_date": signup,
            "acquisition_channel": channel,
            "age_band": rng.choice(["18-29", "30-44", "45-59", "60+"], n_customers),
            "region_group": customers_region,
            "initial_segment": segment,
            "onboarding_completed": onboard,
            "account_funded": funded,
        }
    )
    # Assignment occurs on day 2, after funding and before the first-
    # transaction window closes, so eligibility is pre-treatment.
    assign_date = signup + pd.Timedelta(days=2)
    experiments = pd.DataFrame(
        {
            "experiment_id": "activation_nudge_v1",
            "customer_id": ids,
            "assignment_date": assign_date,
            "arm": assignment,
            "eligible": eligible,
        }
    )
    campaign_date = signup + pd.Timedelta(days=60)
    campaign_assignments = pd.DataFrame(
        {
            "campaign_id": "selected_region_retention_v1",
            "customer_id": ids,
            "campaign_date": campaign_date,
            "eligible": campaign_eligible,
            "selected_region": campaign_treated,
            "region_group": customers_region,
            "treatment_probability": campaign_probability,
        }
    )
    events = []
    txs = []
    holdings = []
    exposures = []
    for i, cid in enumerate(ids):
        base = signup[i]
        steps = [("onboarding_completed", 1, onboard[i]), ("account_funded", 2, funded[i])]
        for name, day, present in steps:
            if present:
                events.append((f"e{cid}_{name}", cid, base + pd.Timedelta(days=day), name))
        # App opens are observed behaviour, not a proxy for financial activity.
        for day in range(121):
            if rng.random() < np.clip(0.08 + quality[i] * 0.22, 0.02, 0.35):
                events.append(
                    (
                        f"e{cid}_open_{day}",
                        cid,
                        base + pd.Timedelta(days=day, hours=int(rng.integers(0, 24))),
                        "app_open",
                    )
                )
        if first_tx[i] or late_activation[i]:
            # Late adopters are funded customers whose first meaningful use
            # occurs after the activation experiment window. This preserves
            # the RCT outcome while making overall D30 distinct from sustained
            # D30 among week-one activators.
            first_day = int(rng.integers(3, 8)) if first_tx[i] else int(rng.integers(10, 29))
            txs.append(
                (
                    f"t{cid}_first",
                    cid,
                    base + pd.Timedelta(days=first_day, hours=int(rng.integers(0, 24))),
                    "card_transaction",
                    "groceries",
                    round(float(rng.lognormal(3.2, 0.7)), 2),
                    "settled",
                    "app",
                )
            )
            events.append(
                (
                    f"e{cid}_card_activated",
                    cid,
                    base + pd.Timedelta(days=first_day),
                    "card_activated",
                )
            )
            # Duration/rate vary by latent product depth and by the operational
            # period of acquisition, rather than being a single smooth curve.
            cohort_factor = _cohort_seasonality(base)
            operational_factor = _cohort_operational_shock(base)
            duration_base = (
                ground_truth.ENGAGEMENT_SCALE_BASE_DAYS
                + ground_truth.ENGAGEMENT_SCALE_QUALITY_DAYS * quality[i]
            )
            if late_activation[i]:
                duration_base = ground_truth.LATE_ENGAGEMENT_SCALE_DAYS + duration_base * 0.58
            duration_scale = max(
                8.0,
                duration_base
                * cohort_factor
                * operational_factor
                * (0.70 + 0.75 * product_depth[i]),
            )
            natural_duration = max(8, round(rng.exponential(duration_scale)))
            natural_end_day = first_day + natural_duration
            active_days = max(0, min(120, natural_end_day) - first_day)
            rate = (
                ground_truth.POST_ACTIVATION_DAILY_RATE
                * cohort_factor
                * operational_factor
                * (0.68 + 0.62 * product_depth[i])
            )
            count = int(rng.poisson(rate * active_days))
            for j in range(count):
                ts = base + pd.Timedelta(
                    days=first_day + int(rng.integers(1, active_days + 1)),
                    hours=int(rng.integers(0, 24)),
                )
                status = "failed" if rng.random() < 0.07 else "settled"
                txs.append(
                    (
                        f"t{cid}_{j}",
                        cid,
                        ts,
                        rng.choice(_TYPES),
                        rng.choice(_CATEGORIES),
                        round(float(rng.lognormal(3.2, 0.7)), 2),
                        status,
                        "app",
                    )
                )
            # The selected-region campaign is observational. A campaign touch
            # is represented as reactivation only after natural activity ended.
            if campaign_treated[i] and natural_end_day < 60 and rng.random() < 0.32:
                txs.append(
                    (
                        f"t{cid}_regional_campaign",
                        cid,
                        campaign_date[i] + pd.Timedelta(days=int(rng.integers(1, 29))),
                        "card_transaction",
                        "groceries",
                        round(float(rng.lognormal(3.1, 0.6)), 2),
                        "settled",
                        "campaign",
                    )
                )
            # A smaller, non-campaign reactivation pocket is placed near the
            # later observation windows. It yields realistic local bumps while
            # preserving a declining aggregate retention curve.
            if natural_end_day < 58 and rng.random() < (
                ground_truth.REACTIVATION_BASE_RATE
                * product_depth[i]
                * _cohort_reactivation_shock(base)
            ):
                reactivation_shock = _cohort_reactivation_shock(base)
                if reactivation_shock >= 3.0:
                    # A cohort-specific product/campaign wave is concentrated
                    # in the D60 window, creating a local bump rather than a
                    # universal monotonic retention shape.
                    revival_day = int(
                        rng.integers(58, 67) if rng.random() < 0.85 else rng.integers(88, 97)
                    )
                else:
                    revival_day = int(rng.choice([rng.integers(58, 67), rng.integers(88, 97)]))
                txs.append(
                    (
                        f"t{cid}_reactivation",
                        cid,
                        base + pd.Timedelta(days=revival_day, hours=int(rng.integers(0, 24))),
                        "card_transaction",
                        "retail",
                        round(float(rng.lognormal(3.1, 0.6)), 2),
                        "settled",
                        "app",
                    )
                )
        elif funded[i] and rng.random() < 0.10:
            # Failed attempts make the funnel and transaction quality checks meaningful.
            ts = base + pd.Timedelta(
                days=int(rng.integers(2 if eligible[i] else 0, 8)),
                hours=int(rng.integers(0, 24)),
            )
            txs.append(
                (
                    f"t{cid}_failed_first",
                    cid,
                    ts,
                    "card_transaction",
                    "retail",
                    round(float(rng.lognormal(3.2, 0.7)), 2),
                    "failed",
                    "app",
                )
            )
        if funded[i]:
            holdings.append(
                (f"h{cid}_current", cid, "current_account", base + pd.Timedelta(days=2))
            )
        if rng.random() < np.clip(product_depth[i] * 0.52, 0.02, 0.75):
            holdings.append(
                (
                    f"h{cid}_savings",
                    cid,
                    "savings",
                    base + pd.Timedelta(days=int(rng.integers(5, 50))),
                )
            )
        if eligible[i]:
            exposures.append((f"x{cid}", cid, "activation_nudge_v1", assign_date[i], assignment[i]))
        if campaign_treated[i]:
            exposures.append(
                (
                    f"xregional{cid}",
                    cid,
                    "selected_region_retention_v1",
                    campaign_date[i],
                    "treatment",
                )
            )
    event_df = pd.DataFrame(
        events, columns=["event_id", "customer_id", "event_timestamp", "event_type"]
    )
    tx_df = pd.DataFrame(
        txs,
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
    hold_df = pd.DataFrame(
        holdings, columns=["holding_id", "customer_id", "product_type", "opened_at"]
    )
    exp_df = pd.DataFrame(
        exposures,
        columns=["exposure_id", "customer_id", "campaign_id", "exposure_timestamp", "arm"],
    )
    # Outcomes use the same observable calendar-day contract as the Python and
    # SQL activation marts: funded plus a settled meaningful transaction in
    # signup days 0-7 inclusive. D30 is a separate overall retention measure.
    observed = tx_df.loc[
        tx_df["status"].eq("settled") & tx_df["transaction_type"].isin(_TYPES)
    ].merge(customers[["customer_id", "signup_date", "account_funded"]], on="customer_id")
    observed["day_from_signup"] = (
        pd.to_datetime(observed["timestamp"]).dt.normalize()
        - pd.to_datetime(observed["signup_date"]).dt.normalize()
    ).dt.days
    activated_ids = set(
        observed.loc[
            observed["account_funded"] & observed["day_from_signup"].between(0, 7),
            "customer_id",
        ]
    )
    d30_ids = set(observed.loc[observed["day_from_signup"].between(30, 36), "customer_id"])
    transaction_counts = tx_df.assign(
        in_first_week=lambda frame: (
            frame["timestamp"].dt.normalize().to_numpy()
            <= customers.set_index("customer_id")
            .loc[frame["customer_id"], "signup_date"]
            .to_numpy()
            + pd.Timedelta(days=7)
        )
    )
    failed_first_week = (
        transaction_counts.loc[
            transaction_counts["status"].eq("failed") & transaction_counts["in_first_week"]
        ]
        .groupby("customer_id")
        .size()
    )
    attempted_first_week = (
        transaction_counts.loc[transaction_counts["in_first_week"]].groupby("customer_id").size()
    )
    failed_rate = (
        (failed_first_week / attempted_first_week).reindex(ids, fill_value=0.0).fillna(0.0)
    )
    outcomes = pd.DataFrame(
        {
            "experiment_id": "activation_nudge_v1",
            "customer_id": ids,
            "first_week_activation": pd.Series(ids).isin(activated_ids).to_numpy(),
            "d30_active": pd.Series(ids).isin(d30_ids).to_numpy(),
            "d30_sustained_engagement": pd.Series(ids).isin(activated_ids & d30_ids).to_numpy(),
            "support_contacts": rng.poisson(0.06 + (assignment == "treatment") * 0.015),
            "failed_payment_rate": failed_rate.to_numpy(),
            "incentive_cost": np.where(assignment == "treatment", 0.35, 0.0),
        }
    )
    return {
        "customers": customers,
        "customer_events": event_df,
        "transactions": tx_df,
        "product_holdings": hold_df,
        "marketing_exposures": exp_df,
        "experiment_assignments": experiments,
        "experiment_outcomes": outcomes,
        "campaign_assignments": campaign_assignments,
    }


def write_dataset(tables: dict[str, pd.DataFrame], output: str | Path) -> None:
    path = Path(output)
    path.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_parquet(path / f"{name}.parquet", index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="dev")
    parser.add_argument("--output", default="data/generated")
    args = parser.parse_args()
    with open("config/profiles.yml", encoding="utf-8") as fh:
        profile = yaml.safe_load(fh)["profiles"][args.profile]
    write_dataset(generate_dataset(profile["customers"], profile["seed"]), args.output)


if __name__ == "__main__":
    main()
