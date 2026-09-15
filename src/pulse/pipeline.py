"""Reproducible end-to-end analytical build for the synthetic Pulse dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from pulse.analytics.analysis import (
    experiment_analysis,
    journey_analysis,
    rct_diagnostics,
    retention_cohorts,
    selected_region_campaign_analysis,
)
from pulse.analytics.plots import (
    calibration,
    cohort_retention,
    did_trends,
    drift,
    effect_ci,
    funnel,
    lift,
    model_comparison,
    model_performance_over_time,
    strategy_value,
)
from pulse.economics import economics_sensitivity, strategy_comparison
from pulse.features.temporal import build_churn_snapshots
from pulse.models.churn import train_churn_models, train_response_propensity
from pulse.models.evaluation import calibration_table, ranking_table
from pulse.monitoring.drift import performance_over_time, stability_report
from pulse.simulation.generator import generate_dataset, write_dataset
from pulse.warehouse import build_warehouse, run_analysis, run_models, run_validation


def _native(value: object) -> object:
    if isinstance(value, dict):
        return {key: _native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    if pd.isna(value):
        return None
    return value


def run_pipeline(
    *,
    profile: str = "dev",
    data_dir: str | Path = "data/generated",
    artifact_dir: str | Path = "artifacts",
) -> dict[str, object]:
    profiles = {"ci": 2_000, "dev": 20_000, "full": 100_000}
    if profile not in profiles:
        raise ValueError(f"unknown profile: {profile}")
    data_path, artifacts = Path(data_dir), Path(artifact_dir)
    tables = generate_dataset(profiles[profile], seed=1729)
    write_dataset(tables, data_path)
    table_dir, figure_dir = artifacts / "tables", artifacts / "figures"
    table_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    journey = journey_analysis(
        tables["customers"], tables["customer_events"], tables["transactions"]
    )
    cohorts = retention_cohorts(tables["customers"], tables["transactions"])
    experiment, experiment_stats = experiment_analysis(
        tables["experiment_assignments"], tables["experiment_outcomes"]
    )
    rct_balance, rct_guardrails, rct_power = rct_diagnostics(
        tables["experiment_assignments"], tables["experiment_outcomes"], tables["customers"]
    )
    campaign = selected_region_campaign_analysis(
        tables["customers"], tables["transactions"], tables["campaign_assignments"]
    )
    snapshots = build_churn_snapshots(
        tables["customers"],
        tables["transactions"],
        tables["product_holdings"],
        tables["customer_events"],
    )
    churn = train_churn_models(snapshots)
    selected_model = "regularized_logistic"
    probabilities = churn["probabilities"][selected_model]
    calibration_data = calibration_table(churn["test_target"], probabilities)
    lift_data = ranking_table(churn["test_target"], probabilities)
    response = train_response_propensity(
        tables["experiment_assignments"], tables["experiment_outcomes"], tables["customers"]
    )
    economic_population = churn["split"].test[["customer_id", "gross_volume_30d"]].copy()
    economic_population["churn_probability"] = probabilities.to_numpy()
    economic_population = economic_population.merge(
        tables["customers"][
            [
                "customer_id",
                "acquisition_channel",
                "initial_segment",
                "account_funded",
                "onboarding_completed",
            ]
        ],
        on="customer_id",
        how="left",
    )
    response_features = [
        "acquisition_channel",
        "initial_segment",
        "account_funded",
        "onboarding_completed",
    ]
    economic_population["response_probability"] = response["model"].predict_proba(
        economic_population[response_features]
    )[:, 1]
    economic_population["customer_value"] = (economic_population["gross_volume_30d"] * 0.0025).clip(
        lower=1.0
    )
    config_path = Path(__file__).resolve().parents[2] / "config" / "economics.yml"
    economics_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["unit_economics"]
    economics = strategy_comparison(
        economic_population,
        churn_col="churn_probability",
        response_col="response_probability",
        value_col="customer_value",
        **economics_config,
    )
    sensitivity = economics_sensitivity(
        economic_population,
        churn_col="churn_probability",
        response_col="response_probability",
        value_col="customer_value",
        **economics_config,
    )
    monitoring = stability_report(
        churn["split"].train,
        churn["split"].test,
        probabilities,
        churn["test_target"],
        churn["features"],
    )
    monitoring_performance = performance_over_time(
        churn["split"].test,
        probabilities,
        churn["test_target"],
    )
    # SQL is a first-class independently materialized path, not an unused model layer.
    database = artifacts / "pulse.duckdb"
    con = build_warehouse(data_path, database)
    try:
        sql_root = Path(__file__).resolve().parents[2] / "sql"
        run_models(con, sql_root)
        run_validation(con, sql_root)
        sql_outputs = run_analysis(con, sql_root)
    finally:
        con.close()
    outputs = {
        "journey": journey,
        "retention_cohorts": cohorts,
        "experiment_summary": experiment,
        "churn_model_comparison": churn["comparison"],
        "churn_calibration": calibration_data,
        "churn_lift": lift_data,
        "monitoring": monitoring,
        "monitoring_performance": monitoring_performance,
        "response_propensity_metrics": pd.DataFrame([response["metrics"]]),
        "rct_balance": rct_balance,
        "rct_guardrails": rct_guardrails,
        "campaign_weekly_trends": campaign["weekly_trends"],
        "campaign_estimates": pd.DataFrame(
            [
                {
                    **campaign["did"],
                    **campaign["iptw_effect"],
                    "effective_sample_size": campaign["effective_sample_size"],
                }
            ]
        ),
        "campaign_pretrend": campaign["pretrend"],
        "campaign_iptw_balance": campaign["balance"],
        "campaign_overlap": campaign["overlap"],
        "campaign_weight_summary": campaign["weights"],
        "targeting_strategy_comparison": economics,
        "economics_sensitivity": sensitivity,
    }
    outputs.update({f"sql_{name}": table for name, table in sql_outputs.items()})
    for name, table in outputs.items():
        table.to_csv(table_dir / f"{name}.csv", index=False)
    funnel(journey, figure_dir / "journey_funnel")
    cohort_retention(cohorts, figure_dir / "cohort_retention")
    calibration(calibration_data, figure_dir / "churn_calibration")
    lift(lift_data, figure_dir / "churn_lift")
    effect_ci(experiment_stats, figure_dir / "rct_effect_ci")
    did_trends(campaign["weekly_trends"], figure_dir / "campaign_weekly_trends")
    strategy_value(economics, figure_dir / "targeting_strategy_value")
    drift(monitoring, figure_dir / "drift_over_time")
    model_performance_over_time(monitoring_performance, figure_dir / "model_performance_over_time")
    model_comparison(churn["comparison"], figure_dir / "churn_model_comparison")
    treatment = experiment.set_index("arm").loc["treatment"]
    control = experiment.set_index("arm").loc["control"]
    model_row = churn["comparison"].set_index("model").loc[selected_model].to_dict()
    for count_field in ("evaluation_customers", "evaluation_events", "top_decile_customers"):
        model_row[count_field] = int(model_row[count_field])
    performance_status = {
        "useful": bool(model_row["roc_auc"] > 0.5 and model_row["lift_at_10pct"] > 1.0),
        "recalibration_indication": bool(monitoring_performance["calibration_error"].max() >= 0.05),
        "retraining_indication": bool(
            len(monitoring_performance) >= 2
            and (
                monitoring_performance.iloc[-1]["roc_auc"]
                < monitoring_performance.iloc[0]["roc_auc"] - 0.05
                or monitoring_performance.iloc[-1]["lift_at_10pct"] < 1.0
            )
        ),
    }
    best_strategy = economics.loc[economics["expected_net_value"].idxmax()]
    results = {
        "schema_version": "1.0",
        "dataset": {
            "synthetic": True,
            "customers": len(tables["customers"]),
            "date_start": str(pd.to_datetime(tables["customers"]["signup_date"]).min().date()),
            "date_end": str(pd.to_datetime(tables["transactions"]["timestamp"]).max().date()),
        },
        "journey": {
            "activation_rate": float(
                journey.set_index("stage").loc["first_transaction_7d", "conversion_from_signup"]
            ),
            "d30_retention": float(
                journey.set_index("stage").loc["d30_retention_overall", "conversion_from_signup"]
            ),
            "sequential_sustained_engagement_d30": float(
                journey.set_index("stage").loc["sustained_engagement_d30", "conversion_from_signup"]
            ),
            "activation_contract": "Funded and at least one settled meaningful transaction in signup calendar days 0-7 inclusive.",
            "retention_windows": {"d7": "D7-13", "d30": "D30-36", "d60": "D60-66", "d90": "D90-96"},
            "mature_retention": {
                f"d{horizon}": float(
                    cohorts.loc[cohorts["horizon_days"].eq(horizon), "retention"].mean()
                )
                for horizon in (7, 30, 60, 90)
            },
        },
        "experiment": {
            "primary_metric": "first_week_activation",
            "control_customers": int(control.customers),
            "treatment_customers": int(treatment.customers),
            "control_activations": int(control.activations),
            "treatment_activations": int(treatment.activations),
            "control_rate": control.activation_rate,
            "treatment_rate": treatment.activation_rate,
            **experiment_stats,
            **rct_power,
            "claim_scope": "Randomized experiment estimate for eligible customers.",
        },
        "churn_model": {
            "selected_model": selected_model,
            "selection_rule": "Regularized logistic is fixed as the selected operational model for interpretability; the comparison table remains the evaluation record.",
            **model_row,
            "claim_scope": "Predictive association on a later temporal holdout, not causal effect.",
        },
        "model_comparison": {
            "table": "churn_model_comparison.csv",
            "figure": "churn_model_comparison.svg",
            "evaluation": "later temporal holdout",
        },
        "response_propensity": {
            **response["metrics"],
            "model_target": "Treated-outcome propensity: observed activation probability among treated eligible customers.",
            "claim_scope": "Predictive association among treated, eligible customers; not incremental treatment benefit.",
        },
        "monitoring": {
            "max_feature_psi": monitoring.loc[monitoring.kind.eq("feature_drift"), "value"].max(),
            "table": "monitoring.csv",
            "figure": "drift_over_time.svg",
            "performance_table": "monitoring_performance.csv",
            "performance_figure": "model_performance_over_time.svg",
            "selected_model": selected_model,
            "status": performance_status,
            "evidence": {
                "holdout_months": len(monitoring_performance),
                "mean_base_rate": float(monitoring_performance["base_rate"].mean()),
                "max_calibration_error": float(monitoring_performance["calibration_error"].max()),
                "min_roc_auc": float(monitoring_performance["roc_auc"].min()),
                "min_lift_at_10pct": float(monitoring_performance["lift_at_10pct"].min()),
            },
        },
        "causal": {
            "design": "selected-region observational campaign; DiD plus stabilized IPTW diagnostics",
            "comparison_customers": int(
                campaign["weekly_trends"]
                .loc[campaign["weekly_trends"]["treatment"].eq(0), "customers"]
                .iloc[0]
            ),
            "selected_region_customers": int(
                campaign["weekly_trends"]
                .loc[campaign["weekly_trends"]["treatment"].eq(1), "customers"]
                .iloc[0]
            ),
            **campaign["did"],
            **campaign["iptw_effect"],
            "effective_sample_size": campaign["effective_sample_size"],
            "pretrend_table": "campaign_pretrend.csv",
            "overlap_table": "campaign_overlap.csv",
            "balance_table": "campaign_iptw_balance.csv",
            "trust_status": campaign["trust_status"],
            "claim_scope": "Observational estimate subject to overlap, measured balance, and parallel-trends limitations.",
        },
        "economics": {
            "assumptions": economics_config,
            "strategy_table": "targeting_strategy_comparison.csv",
            "sensitivity_table": "economics_sensitivity.csv",
            "decision_summary": {
                "best_strategy": str(best_strategy["strategy"]),
                "evaluated_population": len(economic_population),
                "customers_contacted": int(best_strategy["customers_contacted"]),
                "contact_rate": float(best_strategy["contact_rate"]),
                "expected_net_value": float(best_strategy["expected_net_value"]),
                "expected_net_value_per_10k": float(
                    best_strategy["expected_net_value"] / len(economic_population) * 10_000
                ),
            },
            "claim_scope": "Scenario analysis conditional on stated fictional unit-economics assumptions.",
        },
        "sql_evidence": {
            "database": "pulse.duckdb",
            "tables": [f"sql_{name}.csv" for name in sql_outputs],
        },
        "limitations": [
            "All data are behaviourally plausible synthetic simulation.",
            "Observational associations are not causal claims.",
        ],
    }
    (artifacts / "results.json").write_text(
        json.dumps(_native(results), indent=2) + "\n", encoding="utf-8"
    )
    return _native(results)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="dev", choices=["ci", "dev", "full"])
    parser.add_argument("--data-dir", default="data/generated")
    parser.add_argument("--artifact-dir", default="artifacts")
    args = parser.parse_args()
    run_pipeline(profile=args.profile, data_dir=args.data_dir, artifact_dir=args.artifact_dir)


if __name__ == "__main__":
    main()
