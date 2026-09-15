"""Decision-oriented journey, cohort, and experiment analyses."""

from __future__ import annotations

from math import erf, sqrt

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from pulse.causal import (
    balance_table,
    difference_in_differences,
    effective_sample_size,
    stabilized_iptw_weights,
)
from pulse.experimentation.power import minimum_detectable_effect, two_proportion_z_test


def journey_analysis(
    customers: pd.DataFrame, events: pd.DataFrame, transactions: pd.DataFrame
) -> pd.DataFrame:
    customer_ids = set(customers["customer_id"])
    event_sets = {
        name: set(events.loc[events["event_type"].eq(name), "customer_id"])
        for name in ["onboarding_completed", "account_funded"]
    }
    meaningful_types = ["card_transaction", "transfer", "bill_payment"]
    tx = transactions.loc[
        transactions["status"].eq("settled")
        & transactions["transaction_type"].isin(meaningful_types)
    ].copy()
    tx["activity_date"] = pd.to_datetime(tx["timestamp"]).dt.normalize()
    customer_dates = customers[["customer_id", "signup_date", "account_funded"]].copy()
    customer_dates["signup_date"] = pd.to_datetime(customer_dates["signup_date"]).dt.normalize()
    tx = tx.merge(customer_dates, on="customer_id", how="inner")
    tx["day_from_signup"] = (tx["activity_date"] - tx["signup_date"]).dt.days
    first_week = tx["day_from_signup"].between(0, 7)
    d30_window = tx["day_from_signup"].between(30, 36)
    activated = set(tx.loc[first_week & tx["account_funded"], "customer_id"])
    d30 = set(tx.loc[d30_window, "customer_id"])
    repeated = tx.groupby("customer_id")["transaction_id"].nunique()
    stages = [
        ("signup", customer_ids),
        ("onboarding_completed", event_sets["onboarding_completed"]),
        ("account_funded", event_sets["account_funded"]),
        (
            "first_transaction_7d",
            activated,
        ),
        ("repeat_usage", activated & set(repeated[repeated >= 2].index)),
        ("sustained_engagement_d30", activated & d30),
    ]
    rows = []
    previous = len(customer_ids)
    for stage, ids in stages:
        count = len(ids)
        rows.append(
            {
                "stage": stage,
                "customers": count,
                "conversion_from_signup": count / len(customer_ids),
                "dropoff_from_previous": previous - count,
                "conversion_from_previous": count / previous if previous else 0.0,
                "metric_scope": "sequential_funnel",
            }
        )
        previous = count
    # Overall D30 retention is deliberately reported separately: it retains the
    # full signup denominator and must not be interpreted as a funnel step.
    rows.append(
        {
            "stage": "d30_retention_overall",
            "customers": len(d30),
            "conversion_from_signup": len(d30) / len(customer_ids),
            "dropoff_from_previous": pd.NA,
            "conversion_from_previous": pd.NA,
            "metric_scope": "overall_retention",
        }
    )
    return pd.DataFrame(rows)


def retention_cohorts(customers: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    data = customers[["customer_id", "signup_date", "acquisition_channel"]].copy()
    data["signup_date"] = pd.to_datetime(data["signup_date"]).dt.normalize()
    data["cohort_month"] = data["signup_date"].dt.to_period("M").astype(str)
    meaningful_types = ["card_transaction", "transfer", "bill_payment"]
    # Older lightweight fixtures omit transaction_type; production observed
    # data always includes it and is filtered explicitly by the canonical rule.
    type_mask = (
        transactions["transaction_type"].isin(meaningful_types)
        if "transaction_type" in transactions
        else pd.Series(True, index=transactions.index)
    )
    tx = transactions.loc[
        transactions["status"].eq("settled") & type_mask,
        ["customer_id", "timestamp"],
    ].copy()
    tx["activity_date"] = pd.to_datetime(tx["timestamp"]).dt.normalize()
    tx = tx.drop(columns="timestamp")
    joined = data.merge(tx, on="customer_id", how="left")
    # A horizon is shown only for customers whose entire inclusive window is
    # observable. This prevents recent signups from being mislabeled inactive.
    analysis_end = tx["activity_date"].max() if not tx.empty else data["signup_date"].min()
    output = []
    for horizon in (7, 30, 60, 90):
        mature = data["signup_date"] + pd.Timedelta(days=horizon + 6) <= analysis_end
        eligible = data.loc[mature].copy()
        active = joined[
            (joined["activity_date"] >= joined["signup_date"] + pd.Timedelta(days=horizon))
            & (joined["activity_date"] <= joined["signup_date"] + pd.Timedelta(days=horizon + 6))
        ]
        flags = active.groupby("customer_id").size().gt(0).rename("active")
        temp = eligible.merge(flags, left_on="customer_id", right_index=True, how="left").fillna(
            {"active": False}
        )
        result = temp.groupby("cohort_month", as_index=False).agg(
            cohort_size=("customer_id", "size"), retention=("active", "mean")
        )
        result["horizon_days"] = horizon
        result["window_start_day"] = horizon
        result["window_end_day"] = horizon + 6
        result["analysis_end"] = analysis_end.date().isoformat()
        output.append(result)
    return pd.concat(output, ignore_index=True)


def experiment_analysis(
    assignments: pd.DataFrame, outcomes: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, float]]:
    data = assignments.merge(outcomes, on=["experiment_id", "customer_id"], how="inner")
    data = data[data["eligible"] & data["arm"].isin(["control", "treatment"])].copy()
    summary = data.groupby("arm", as_index=False).agg(
        customers=("customer_id", "size"),
        activations=("first_week_activation", "sum"),
        activation_rate=("first_week_activation", "mean"),
        d30_rate=("d30_active", "mean"),
        sustained_engagement_d30_rate=("d30_sustained_engagement", "mean"),
    )
    treatment = summary.set_index("arm").loc["treatment"]
    control = summary.set_index("arm").loc["control"]
    stats = two_proportion_z_test(
        int(treatment.activations),
        int(treatment.customers),
        int(control.activations),
        int(control.customers),
    )
    return summary, stats


def rct_diagnostics(
    assignments: pd.DataFrame, outcomes: pd.DataFrame, customers: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """RCT covariate balance, power/MDE, and operational guardrails."""
    data = assignments.merge(customers, on="customer_id", how="inner")
    data = data.loc[data["eligible"] & data["arm"].isin(["control", "treatment"])].copy()
    data["treatment"] = data["arm"].eq("treatment").astype(int)
    covariates = pd.get_dummies(
        data[
            [
                "treatment",
                "account_funded",
                "onboarding_completed",
                "acquisition_channel",
                "initial_segment",
            ]
        ],
        columns=["acquisition_channel", "initial_segment"],
        dtype=float,
    )
    balance = balance_table(
        covariates,
        treatment_col="treatment",
        covariates=[c for c in covariates if c != "treatment"],
    )
    merged = data.merge(outcomes, on=["experiment_id", "customer_id"], how="inner")
    counts = merged.groupby("arm")["customer_id"].size()
    control_rate = float(merged.loc[merged["arm"].eq("control"), "first_week_activation"].mean())
    mde = minimum_detectable_effect(control_rate, int(counts.min()))
    assigned_treatment_share = float(counts["treatment"] / counts.sum())
    expected_share, srm_tolerance, srm_alpha = 0.50, 0.02, 0.01
    srm_z = (assigned_treatment_share - expected_share) / sqrt(
        expected_share * (1 - expected_share) / counts.sum()
    )
    srm_p_value = 2 * (1 - ((1 + erf(abs(srm_z) / sqrt(2))) / 2))
    operational = merged.groupby("arm", as_index=True).agg(
        support_contacts=("support_contacts", "mean"),
        failed_payment_rate=("failed_payment_rate", "mean"),
        incentive_cost=("incentive_cost", "mean"),
    )
    treatment_ops, control_ops = operational.loc["treatment"], operational.loc["control"]
    guardrails = pd.DataFrame(
        [
            {
                "guardrail": "sample_ratio_mismatch",
                "value": assigned_treatment_share,
                "threshold": srm_tolerance,
                "p_value": srm_p_value,
                "status": "pass"
                if abs(assigned_treatment_share - expected_share) <= srm_tolerance
                and srm_p_value >= srm_alpha
                else "review",
                "definition": "Prespecified expected 50:50 allocation, two-sided alpha=0.01, absolute tolerance=0.02.",
            },
            {
                "guardrail": "max_absolute_smd",
                "value": float(balance["standardized_mean_difference"].abs().max()),
                "threshold": 0.10,
                "p_value": np.nan,
                "status": "pass"
                if balance["standardized_mean_difference"].abs().max() <= 0.10
                else "review",
            },
            {
                "guardrail": "minimum_detectable_effect",
                "value": mde,
                "threshold": 0.0,
                "status": "context",
                "p_value": np.nan,
                "definition": "Normal-approximation MDE, not a pass/fail safety guardrail.",
            },
            {
                "guardrail": "support_contact_rate_difference",
                "value": float(treatment_ops.support_contacts - control_ops.support_contacts),
                "threshold": 0.05,
                "p_value": np.nan,
                "status": "pass"
                if treatment_ops.support_contacts - control_ops.support_contacts <= 0.05
                else "review",
                "definition": "Treatment minus control mean support contacts per eligible customer.",
            },
            {
                "guardrail": "failed_payment_rate_difference",
                "value": float(treatment_ops.failed_payment_rate - control_ops.failed_payment_rate),
                "threshold": 0.03,
                "p_value": np.nan,
                "status": "pass"
                if treatment_ops.failed_payment_rate - control_ops.failed_payment_rate <= 0.03
                else "review",
                "definition": "Treatment minus control first-week failed-attempt rate.",
            },
            {
                "guardrail": "incentive_cost_per_customer",
                "value": float(treatment_ops.incentive_cost),
                "threshold": 0.50,
                "p_value": np.nan,
                "status": "pass" if treatment_ops.incentive_cost <= 0.50 else "review",
                "definition": "Mean fictional incentive currency units per treated eligible customer.",
            },
        ]
    )
    return balance, guardrails, {"mde": mde, "eligible_per_arm": float(counts.min())}


def selected_region_campaign_analysis(
    customers: pd.DataFrame, transactions: pd.DataFrame, campaign_assignments: pd.DataFrame
) -> dict[str, object]:
    """Analyze the selected-region campaign as observational DiD plus IPTW diagnostics."""
    base = campaign_assignments.loc[campaign_assignments["eligible"]].merge(
        customers[["customer_id", "acquisition_channel", "initial_segment", "age_band"]],
        on="customer_id",
    )
    base["treatment"] = base["selected_region"].astype(int)
    tx = transactions.loc[transactions["status"].eq("settled")].copy()
    tx["timestamp"] = pd.to_datetime(tx["timestamp"])
    # Each row is a customer-relative weekly activity indicator. Weeks -4..-1
    # are the explicit pre-trend diagnostic; 0..3 are campaign follow-up.
    weeks = pd.DataFrame({"relative_week": range(-4, 4)})
    panel = base[["customer_id", "treatment", "campaign_date"]].merge(weeks, how="cross")
    panel["week_start"] = pd.to_datetime(panel["campaign_date"]) + pd.to_timedelta(
        panel["relative_week"] * 7, unit="D"
    )
    panel["week_end"] = panel["week_start"] + pd.Timedelta(days=7)
    joined = panel.merge(tx[["customer_id", "timestamp"]], on="customer_id", how="left")
    active = (
        joined.loc[
            (joined["timestamp"] >= joined["week_start"])
            & (joined["timestamp"] < joined["week_end"])
        ]
        .groupby(["customer_id", "relative_week"])
        .size()
        .gt(0)
        .rename("active")
    )
    panel = panel.merge(
        active, left_on=["customer_id", "relative_week"], right_index=True, how="left"
    )
    panel["active"] = panel["active"].fillna(False).astype(int)
    panel["post"] = panel["relative_week"].ge(0).astype(int)
    trends = panel.groupby(["relative_week", "treatment"], as_index=False).agg(
        active_rate=("active", "mean"), customers=("customer_id", "nunique")
    )
    pretrend = trends.pivot(
        index="relative_week", columns="treatment", values="active_rate"
    ).reset_index()
    pretrend["treated_minus_control"] = pretrend.get(1, 0.0) - pretrend.get(0, 0.0)
    pretrend["period"] = pretrend["relative_week"].map(lambda w: "post" if w >= 0 else "pre")
    did = difference_in_differences(
        panel, group_col="treatment", post_col="post", outcome_col="active"
    )
    pre_counts = panel.loc[panel["relative_week"].lt(0)].groupby("customer_id")["active"].sum()
    covariates = base.merge(
        pre_counts.rename("pre_active_weeks"), on="customer_id", how="left"
    ).fillna({"pre_active_weeks": 0})
    encoded = pd.get_dummies(
        covariates[["acquisition_channel", "initial_segment", "age_band", "region_group"]],
        dtype=float,
    )
    propensity = (
        LogisticRegression(C=1.0, max_iter=300, random_state=1729)
        .fit(encoded, covariates["treatment"])
        .predict_proba(encoded)[:, 1]
    )
    covariates["propensity"] = propensity
    covariates["stabilized_iptw"] = stabilized_iptw_weights(
        covariates["treatment"], covariates["propensity"]
    )
    balance_input = pd.concat(
        [covariates[["treatment", "stabilized_iptw", "pre_active_weeks"]], encoded], axis=1
    )
    balance_unweighted = balance_table(
        balance_input,
        treatment_col="treatment",
        covariates=[c for c in balance_input if c not in {"treatment", "stabilized_iptw"}],
    ).assign(weighting="unweighted")
    balance_weighted = balance_table(
        balance_input,
        treatment_col="treatment",
        covariates=[c for c in balance_input if c not in {"treatment", "stabilized_iptw"}],
        weight_col="stabilized_iptw",
    ).assign(weighting="stabilized_iptw")
    balance = pd.concat([balance_unweighted, balance_weighted], ignore_index=True)
    overlap_bins = (
        covariates.assign(
            propensity_bin=pd.cut(
                covariates["propensity"],
                bins=[0, 0.1, 0.2, 0.4, 0.6, 0.8, 0.9, 1],
                include_lowest=True,
            )
        )
        .groupby(["propensity_bin", "treatment"], observed=False)
        .size()
        .rename("customers")
        .reset_index()
    )
    treated_propensity = covariates.loc[covariates["treatment"].eq(1), "propensity"]
    control_propensity = covariates.loc[covariates["treatment"].eq(0), "propensity"]
    common_lower, common_upper = (
        max(treated_propensity.min(), control_propensity.min()),
        min(treated_propensity.max(), control_propensity.max()),
    )
    in_common_support = covariates["propensity"].between(common_lower, common_upper)
    overlap_share = float(in_common_support.mean())
    weighted_max_smd = float(balance_weighted["standardized_mean_difference"].abs().max())
    trust_status = "pass" if overlap_share >= 0.95 and weighted_max_smd <= 0.10 else "review"
    overlap = pd.concat(
        [
            overlap_bins.assign(
                diagnostic="bin_count", value=np.nan, threshold=np.nan, status="context"
            ),
            pd.DataFrame(
                [
                    {
                        "propensity_bin": "common_support_share",
                        "treatment": pd.NA,
                        "customers": len(covariates),
                        "diagnostic": "common_support_share",
                        "value": overlap_share,
                        "threshold": 0.95,
                        "status": "pass" if overlap_share >= 0.95 else "review",
                    },
                    {
                        "propensity_bin": "weighted_max_absolute_smd",
                        "treatment": pd.NA,
                        "customers": len(covariates),
                        "diagnostic": "weighted_max_absolute_smd",
                        "value": weighted_max_smd,
                        "threshold": 0.10,
                        "status": "pass" if weighted_max_smd <= 0.10 else "review",
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    customer_panel = (
        panel.groupby(["customer_id", "treatment", "post"], as_index=False)
        .agg(active=("active", "mean"))
        .merge(covariates[["customer_id", "stabilized_iptw"]], on="customer_id")
    )
    grouped = customer_panel.groupby(["treatment", "post"])
    weighted_means = grouped.apply(
        lambda group: np.average(group["active"], weights=group["stabilized_iptw"]),
        include_groups=False,
    )
    weighted_effect = (weighted_means[1, 1] - weighted_means[1, 0]) - (
        weighted_means[0, 1] - weighted_means[0, 0]
    )
    # Bounded independence approximation on customer-level pre/post averages.
    cell_variances = grouped.apply(
        lambda group: np.average(
            (group["active"] - np.average(group["active"], weights=group["stabilized_iptw"])) ** 2,
            weights=group["stabilized_iptw"],
        ),
        include_groups=False,
    )
    cell_ess = grouped["stabilized_iptw"].apply(effective_sample_size)
    weighted_se = sqrt(sum(cell_variances[key] / cell_ess[key] for key in cell_variances.index))
    weighted_iptw = {
        "iptw_did_effect": float(weighted_effect),
        "iptw_standard_error": float(weighted_se),
        "iptw_ci_low": float(weighted_effect - 1.96 * weighted_se),
        "iptw_ci_high": float(weighted_effect + 1.96 * weighted_se),
        "uncertainty_method": "normal approximation on weighted customer-week means; ignores within-customer correlation",
    }
    weights = (
        covariates["stabilized_iptw"]
        .describe(percentiles=[0.01, 0.5, 0.99])
        .rename_axis("statistic")
        .reset_index(name="weight")
    )
    return {
        "weekly_trends": trends,
        "pretrend": pretrend,
        "balance": balance,
        "overlap": overlap,
        "weights": weights,
        "did": did,
        "iptw_effect": weighted_iptw,
        "effective_sample_size": effective_sample_size(covariates["stabilized_iptw"]),
        "trust_status": trust_status,
    }
