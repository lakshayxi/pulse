"""Build the evidence include used by the reviewer-facing LaTeX report.

The report is a presentation layer over the frozen pipeline artifacts. This
script reads the manifest, CSV tables, and external evidence registry. It does
not rerun analysis or mutate analytical artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _get(mapping: dict[str, Any], path: str) -> Any:
    current: Any = mapping
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"results.json is missing required key: {path}")
        current = current[key]
    return current


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"required table is empty: {path}")
    return rows


def _tex(value: Any) -> str:
    """Escape plain text for LaTeX while retaining exact identifiers and URLs."""

    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def _pct(value: Any, digits: int = 1) -> str:
    return f"{float(value) * 100:.{digits}f}%"


def _pp(value: Any, digits: int = 2) -> str:
    return f"{float(value) * 100:+.{digits}f} pp"


def _num(value: Any, digits: int = 2) -> str:
    return f"{float(value):,.{digits}f}"


def _integer(value: Any) -> str:
    return f"{round(float(value)):,.0f}"


def _pvalue(value: Any) -> str:
    numeric = float(value)
    return r"$p < 0.001$" if numeric < 0.001 else f"$p={numeric:.3f}$"


def _load(
    root: Path,
) -> tuple[
    dict[str, Any],
    dict[str, list[dict[str, str]]],
    dict[str, Any],
    dict[str, float],
]:
    results_path = root / "artifacts/results.json"
    results = json.loads(results_path.read_text(encoding="utf-8"))
    table_names = [
        "journey.csv",
        "retention_cohorts.csv",
        "experiment_summary.csv",
        "rct_guardrails.csv",
        "campaign_pretrend.csv",
        "campaign_weekly_trends.csv",
        "campaign_estimates.csv",
        "campaign_overlap.csv",
        "campaign_iptw_balance.csv",
        "churn_model_comparison.csv",
        "response_propensity_metrics.csv",
        "monitoring_performance.csv",
        "targeting_strategy_comparison.csv",
    ]
    tables = {name: _rows(root / "artifacts/tables" / name) for name in table_names}
    registry = yaml.safe_load((root / "config/external_benchmarks.yml").read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or not isinstance(registry.get("benchmarks"), list):
        raise TypeError("external_benchmarks.yml must contain a benchmarks list")
    economics = yaml.safe_load((root / "config/economics.yml").read_text(encoding="utf-8"))
    if not isinstance(economics, dict) or not isinstance(economics.get("unit_economics"), dict):
        raise TypeError("economics.yml must contain a unit_economics mapping")
    return results, tables, registry, economics["unit_economics"]


def _validate(
    results: dict[str, Any],
    tables: dict[str, list[dict[str, str]]],
    economics_config: dict[str, float],
) -> None:
    """Fail closed when report denominators do not agree with frozen artifacts."""

    customers = int(_get(results, "dataset.customers"))
    journey = tables["journey.csv"]
    signup = next(row for row in journey if row["stage"] == "signup")
    sustained = next(row for row in journey if row["stage"] == "sustained_engagement_d30")
    overall = next(row for row in journey if row["stage"] == "d30_retention_overall")
    if int(signup["customers"]) != customers:
        raise ValueError("journey signup denominator does not match dataset.customers")
    sustained_rate = float(_get(results, "journey.sequential_sustained_engagement_d30"))
    if int(sustained["customers"]) != round(customers * sustained_rate):
        raise ValueError("sustained D30 count does not match results.json")
    overall_rate = float(_get(results, "journey.d30_retention"))
    if int(overall["customers"]) != round(customers * overall_rate):
        raise ValueError("overall D30 count does not match results.json")
    cohorts = tables["retention_cohorts.csv"]
    for horizon in (7, 30, 60, 90):
        values = [float(row["retention"]) for row in cohorts if int(row["horizon_days"]) == horizon]
        if not values:
            raise ValueError(f"retention table has no D{horizon} observations")
        expected = sum(values) / len(values)
        if not math.isclose(
            float(_get(results, f"journey.mature_retention.d{horizon}")),
            expected,
            rel_tol=0,
            abs_tol=1e-12,
        ):
            raise ValueError(f"mature D{horizon} retention does not match the cohort table")
    experiment = tables["experiment_summary.csv"]
    by_arm = {row["arm"]: row for row in experiment}
    if set(by_arm) != {"control", "treatment"}:
        raise ValueError("experiment_summary.csv must contain control and treatment arms")
    eligible = float(_get(results, "experiment.eligible_per_arm"))
    if int(by_arm["control"]["customers"]) != round(eligible):
        raise ValueError("results.json eligible_per_arm does not match control arm")
    for arm in ("control", "treatment"):
        if int(by_arm[arm]["customers"]) != int(_get(results, f"experiment.{arm}_customers")):
            raise ValueError(f"{arm} denominator does not match results.json")
        if int(by_arm[arm]["activations"]) != int(_get(results, f"experiment.{arm}_activations")):
            raise ValueError(f"{arm} activation count does not match results.json")
    if int(by_arm["control"]["customers"]) + int(by_arm["treatment"]["customers"]) > customers:
        raise ValueError("experiment arm denominators exceed the dataset population")
    for arm, row in by_arm.items():
        expected_rate = int(row["activations"]) / int(row["customers"])
        if not math.isclose(expected_rate, float(row["activation_rate"]), rel_tol=0, abs_tol=1e-12):
            raise ValueError(f"{arm} activation rate does not match its count and denominator")
        if not math.isclose(
            float(row["activation_rate"]),
            float(_get(results, f"experiment.{arm}_rate")),
            rel_tol=0,
            abs_tol=1e-12,
        ):
            raise ValueError(f"{arm} activation rate does not match results.json")
    control_rate = float(by_arm["control"]["activation_rate"])
    treatment_rate = float(by_arm["treatment"]["activation_rate"])
    risk_difference = treatment_rate - control_rate
    standard_error = math.sqrt(
        control_rate * (1 - control_rate) / int(by_arm["control"]["customers"])
        + treatment_rate * (1 - treatment_rate) / int(by_arm["treatment"]["customers"])
    )
    pooled_rate = (
        int(by_arm["control"]["activations"]) + int(by_arm["treatment"]["activations"])
    ) / (int(by_arm["control"]["customers"]) + int(by_arm["treatment"]["customers"]))
    pooled_standard_error = math.sqrt(
        pooled_rate
        * (1 - pooled_rate)
        * (1 / int(by_arm["control"]["customers"]) + 1 / int(by_arm["treatment"]["customers"]))
    )
    z_statistic = risk_difference / pooled_standard_error
    ci_low = risk_difference - 1.959963984540054 * standard_error
    ci_high = risk_difference + 1.959963984540054 * standard_error
    for key, expected in {
        "risk_difference": risk_difference,
        "z_statistic": z_statistic,
        "ci_low": ci_low,
        "ci_high": ci_high,
    }.items():
        tolerance = 1e-12 if key == "risk_difference" else 1e-10
        if not math.isclose(
            float(_get(results, f"experiment.{key}")), expected, rel_tol=0, abs_tol=tolerance
        ):
            raise ValueError(f"experiment {key} does not reconcile with arm counts")
    calculated_p = math.erfc(abs(z_statistic) / math.sqrt(2))
    recorded_p = float(_get(results, "experiment.p_value"))
    if not (math.isclose(recorded_p, calculated_p, rel_tol=1e-8, abs_tol=1e-12)):
        raise ValueError("experiment p-value does not reconcile with arm counts")
    mde_row = next(
        row
        for row in tables["rct_guardrails.csv"]
        if row["guardrail"] == "minimum_detectable_effect"
    )
    if not math.isclose(
        float(mde_row["value"]),
        float(_get(results, "experiment.mde")),
        rel_tol=0,
        abs_tol=1e-12,
    ):
        raise ValueError("experiment MDE does not match the guardrail table")

    weekly = tables["campaign_weekly_trends.csv"]
    campaign_counts: dict[str, int] = {}
    for treatment, result_key in (
        ("0", "comparison_customers"),
        ("1", "selected_region_customers"),
    ):
        counts = {int(row["customers"]) for row in weekly if row["treatment"] == treatment}
        if len(counts) != 1:
            raise ValueError(f"campaign group {treatment} must have one repeated panel denominator")
        campaign_counts[treatment] = counts.pop()
        if campaign_counts[treatment] != int(_get(results, f"causal.{result_key}")):
            raise ValueError(f"campaign {result_key} does not match results.json")

    weekly_rates = {
        (int(row["relative_week"]), row["treatment"]): float(row["active_rate"]) for row in weekly
    }
    for row in tables["campaign_pretrend.csv"]:
        week = int(row["relative_week"])
        for treatment in ("0", "1"):
            if not math.isclose(
                float(row[treatment]), weekly_rates[(week, treatment)], rel_tol=0, abs_tol=1e-12
            ):
                raise ValueError("campaign pretrend table does not match weekly trends")
    comparison_pre = (
        sum(rate for (week, arm), rate in weekly_rates.items() if week < 0 and arm == "0") / 4
    )
    comparison_post = (
        sum(rate for (week, arm), rate in weekly_rates.items() if week >= 0 and arm == "0") / 4
    )
    treatment_pre = (
        sum(rate for (week, arm), rate in weekly_rates.items() if week < 0 and arm == "1") / 4
    )
    treatment_post = (
        sum(rate for (week, arm), rate in weekly_rates.items() if week >= 0 and arm == "1") / 4
    )
    did_values = {
        "control_pre": comparison_pre,
        "control_post": comparison_post,
        "treated_pre": treatment_pre,
        "treated_post": treatment_post,
        "control_change": comparison_post - comparison_pre,
        "treated_change": treatment_post - treatment_pre,
        "did_effect": (treatment_post - treatment_pre) - (comparison_post - comparison_pre),
    }
    for key, expected in did_values.items():
        if not math.isclose(
            float(_get(results, f"causal.{key}")), expected, rel_tol=0, abs_tol=1e-12
        ):
            raise ValueError(f"campaign {key} does not reconcile with weekly trends")
    estimate_row = tables["campaign_estimates.csv"][0]
    for key in (
        "treated_pre",
        "treated_post",
        "control_pre",
        "control_post",
        "treated_change",
        "control_change",
        "did_effect",
        "iptw_did_effect",
        "iptw_standard_error",
        "iptw_ci_low",
        "iptw_ci_high",
        "effective_sample_size",
    ):
        if not math.isclose(
            float(estimate_row[key]),
            float(_get(results, f"causal.{key}")),
            rel_tol=0,
            abs_tol=1e-12,
        ):
            raise ValueError(f"campaign {key} does not match the estimates table")

    model_rows = {row["model"]: row for row in tables["churn_model_comparison.csv"]}
    selected_model = str(_get(results, "churn_model.selected_model"))
    if selected_model not in model_rows:
        raise ValueError("selected churn model is missing from the comparison table")
    response_row = tables["response_propensity_metrics.csv"][0]
    metric_fields = (
        "brier",
        "roc_auc",
        "pr_auc",
        "lift_at_10pct",
        "capture_at_10pct",
        "precision_at_10pct",
    )
    count_fields = ("evaluation_customers", "evaluation_events", "top_decile_customers")
    for prefix, row in (
        ("churn_model", model_rows[selected_model]),
        ("response_propensity", response_row),
    ):
        for field in metric_fields:
            if not math.isclose(
                float(row[field]),
                float(_get(results, f"{prefix}.{field}")),
                rel_tol=0,
                abs_tol=1e-12,
            ):
                raise ValueError(f"{prefix} {field} does not match results.json")
        for field in count_fields:
            if int(row[field]) != int(_get(results, f"{prefix}.{field}")):
                raise ValueError(f"{prefix} {field} does not match results.json")
    monitored_customers = sum(int(row["customers"]) for row in tables["monitoring_performance.csv"])
    if monitored_customers != int(_get(results, "churn_model.evaluation_customers")):
        raise ValueError("monitoring buckets do not cover the churn evaluation population")

    for key, configured in economics_config.items():
        if not math.isclose(
            float(_get(results, f"economics.assumptions.{key}")),
            float(configured),
            rel_tol=0,
            abs_tol=1e-12,
        ):
            raise ValueError(f"economics assumption {key} does not match economics.yml")
    strategies = tables["targeting_strategy_comparison.csv"]
    evaluated_population = int(_get(results, "economics.decision_summary.evaluated_population"))
    contact_all = next(row for row in strategies if row["strategy"] == "contact_all")
    if int(contact_all["customers_contacted"]) != evaluated_population:
        raise ValueError("economics evaluated population does not match contact_all")
    for row in strategies:
        contacted = int(row["customers_contacted"])
        contact_rate = contacted / evaluated_population
        if not math.isclose(float(row["contact_rate"]), contact_rate, rel_tol=0, abs_tol=1e-12):
            raise ValueError(f"economics contact rate is inconsistent for {row['strategy']}")
        expected_profitable = float(row["expected_net_value"]) > 0
        recorded_profitable = row["profitable"].strip().lower() == "true"
        if recorded_profitable != expected_profitable:
            raise ValueError(f"economics profitability flag is inconsistent for {row['strategy']}")
    best = max(strategies, key=lambda row: float(row["expected_net_value"]))
    decision = _get(results, "economics.decision_summary")
    if best["strategy"] != decision["best_strategy"]:
        raise ValueError("economics best strategy does not match the strategy table")
    for field in ("customers_contacted", "contact_rate", "expected_net_value"):
        if not math.isclose(float(best[field]), float(decision[field]), rel_tol=0, abs_tol=1e-12):
            raise ValueError(f"economics decision {field} does not match the best strategy")
    expected_per_10k = float(best["expected_net_value"]) / evaluated_population * 10_000
    if not math.isclose(
        expected_per_10k,
        float(decision["expected_net_value_per_10k"]),
        rel_tol=0,
        abs_tol=1e-12,
    ):
        raise ValueError("economics decision value per 10k is inconsistent")
    overlap = tables["campaign_overlap.csv"]
    weighted = next(row for row in overlap if row["diagnostic"] == "weighted_max_absolute_smd")
    balance = tables["campaign_iptw_balance.csv"]
    stabilized = [
        abs(float(row["standardized_mean_difference"]))
        for row in balance
        if row["weighting"] == "stabilized_iptw"
    ]
    if not stabilized or not math.isclose(
        float(weighted["value"]), max(stabilized), rel_tol=0, abs_tol=1e-12
    ):
        raise ValueError("weighted max absolute SMD does not match stabilized IPTW balance")


def _rows_tex(rows: list[list[str]]) -> str:
    return "\n".join(" & ".join(row) + r" \\" for row in rows)


def build(root: Path = ROOT, output: Path | None = None) -> Path:
    results, tables, registry, economics_config = _load(root)
    _validate(results, tables, economics_config)
    if output is None:
        output = root / "reports/pulse_case_study_inputs.tex"

    journey = tables["journey.csv"]
    sequential = [row for row in journey if row["metric_scope"] == "sequential_funnel"]
    cohorts = tables["retention_cohorts.csv"]
    june_d30 = next(
        row for row in cohorts if row["cohort_month"] == "2025-06" and row["horizon_days"] == "30"
    )
    june_d60 = next(
        row for row in cohorts if row["cohort_month"] == "2025-06" and row["horizon_days"] == "60"
    )
    if float(june_d60["retention"]) <= float(june_d30["retention"]):
        raise ValueError(
            "June 2025 D60 retention must exceed D30 for the documented reactivation pulse"
        )
    journey_rows = []
    for row in sequential:
        previous = row["conversion_from_previous"]
        previous_text = "--" if previous == "" else _pct(previous, 1)
        journey_rows.append(
            [
                _tex(row["stage"].replace("_", " ")),
                _tex(_integer(row["customers"])),
                _tex(_pct(row["conversion_from_signup"], 1)),
                _tex(previous_text),
            ]
        )

    experiment = {row["arm"]: row for row in tables["experiment_summary.csv"]}
    experiment_rows = []
    for arm in ("control", "treatment"):
        row = experiment[arm]
        experiment_rows.append(
            [
                _tex(arm.title()),
                _tex(_integer(row["customers"])),
                _tex(_integer(row["activations"])),
                _tex(_pct(row["activation_rate"], 1)),
                _tex(_pct(row["d30_rate"], 1)),
                _tex(_pct(row["sustained_engagement_d30_rate"], 1)),
            ]
        )

    guardrail_rows = []
    for row in tables["rct_guardrails.csv"]:
        if row["guardrail"] == "minimum_detectable_effect":
            continue
        threshold = "--" if row["threshold"] == "0.0" else _num(row["threshold"], 3)
        guardrail_rows.append(
            [
                _tex(row["guardrail"].replace("_", " ")),
                _tex(_num(row["value"], 3)),
                _tex(threshold),
                _tex(row["status"]),
            ]
        )

    pretrend_rows = []
    for row in tables["campaign_pretrend.csv"]:
        pretrend_rows.append(
            [
                _tex(row["relative_week"]),
                _tex(_pct(row["0"], 1)),
                _tex(_pct(row["1"], 1)),
                _tex(_pp(row["treated_minus_control"], 2)),
            ]
        )

    models = tables["churn_model_comparison.csv"]
    model_rows = []
    for row in models:
        model_rows.append(
            [
                _tex(row["model"].replace("_", " ")),
                _tex(_num(row["brier"], 3)),
                _tex(_num(row["roc_auc"], 3)),
                _tex(_num(row["pr_auc"], 3)),
                _tex(_num(row["lift_at_10pct"], 3)),
                _tex(_pct(row["capture_at_10pct"], 1)),
            ]
        )

    monitoring_rows = []
    for row in tables["monitoring_performance.csv"]:
        monitoring_rows.append(
            [
                _tex(row["time_bucket"]),
                _tex(_integer(row["customers"])),
                _tex(_pct(row["base_rate"], 1)),
                _tex(_num(row["roc_auc"], 3)),
                _tex(_num(row["lift_at_10pct"], 3)),
                _tex(_num(row["calibration_error"], 3)),
            ]
        )

    economics_rows = []
    for row in tables["targeting_strategy_comparison.csv"]:
        value = _num(row["expected_net_value"], 0)
        if float(row["expected_net_value"]) < 0:
            value = "-" + _num(abs(float(row["expected_net_value"])), 0)
        profitable = "Yes" if row["profitable"].strip().lower() == "true" else "No"
        economics_rows.append(
            [
                _tex(row["strategy"].replace("_", " ")),
                _tex(_integer(row["customers_contacted"])),
                _tex(_pct(row["contact_rate"], 1)),
                _tex(value),
                _tex(profitable),
            ]
        )

    bank_rows = []
    for item in registry["benchmarks"]:
        bank_rows.append(
            [
                _tex(item["bank"]),
                _tex(item["period"]),
                _tex(item["evidence"]),
                _tex(item["implication"]),
            ]
        )

    weighted_value = max(
        abs(float(row["standardized_mean_difference"]))
        for row in tables["campaign_iptw_balance.csv"]
        if row["weighting"] == "stabilized_iptw"
    )
    support = next(
        row for row in tables["campaign_overlap.csv"] if row["diagnostic"] == "common_support_share"
    )

    lines = [
        "% Generated by scripts/build_latex_inputs.py. Do not edit this file.",
        rf"\newcommand{{\DatasetCustomers}}{{{_tex(_integer(_get(results, 'dataset.customers')))}}}",
        rf"\newcommand{{\DatasetStart}}{{{_tex(_get(results, 'dataset.date_start'))}}}",
        rf"\newcommand{{\DatasetEnd}}{{{_tex(_get(results, 'dataset.date_end'))}}}",
        rf"\newcommand{{\ActivationContract}}{{{_tex(_get(results, 'journey.activation_contract'))}}}",
        rf"\newcommand{{\OverallDThirty}}{{{_tex(_pct(_get(results, 'journey.d30_retention'), 3))}}}",
        rf"\newcommand{{\SustainedDThirty}}{{{_tex(_pct(_get(results, 'journey.sequential_sustained_engagement_d30'), 3))}}}",
        rf"\newcommand{{\DThirtyCount}}{{{_tex(_integer(next(row['customers'] for row in journey if row['stage'] == 'd30_retention_overall')))}}}",
        rf"\newcommand{{\SustainedDThirtyCount}}{{{_tex(_integer(next(row['customers'] for row in journey if row['stage'] == 'sustained_engagement_d30')))}}}",
        rf"\newcommand{{\DSevenMature}}{{{_tex(_pct(_get(results, 'journey.mature_retention.d7'), 1))}}}",
        rf"\newcommand{{\DThirtyMature}}{{{_tex(_pct(_get(results, 'journey.mature_retention.d30'), 1))}}}",
        rf"\newcommand{{\DSixtyMature}}{{{_tex(_pct(_get(results, 'journey.mature_retention.d60'), 1))}}}",
        rf"\newcommand{{\DNinetyMature}}{{{_tex(_pct(_get(results, 'journey.mature_retention.d90'), 1))}}}",
        rf"\newcommand{{\JuneDThirty}}{{{_tex(_pct(june_d30['retention'], 2))}}}",
        rf"\newcommand{{\JuneDSixty}}{{{_tex(_pct(june_d60['retention'], 2))}}}",
        rf"\newcommand{{\ControlN}}{{{_tex(_integer(experiment['control']['customers']))}}}",
        rf"\newcommand{{\TreatmentN}}{{{_tex(_integer(experiment['treatment']['customers']))}}}",
        rf"\newcommand{{\ControlRate}}{{{_tex(_pct(_get(results, 'experiment.control_rate'), 2))}}}",
        rf"\newcommand{{\TreatmentRate}}{{{_tex(_pct(_get(results, 'experiment.treatment_rate'), 2))}}}",
        rf"\newcommand{{\RiskDifference}}{{{_tex(_pp(_get(results, 'experiment.risk_difference'), 2))}}}",
        rf"\newcommand{{\RiskCI}}{{{_tex(_pp(_get(results, 'experiment.ci_low'), 2))} to {_tex(_pp(_get(results, 'experiment.ci_high'), 2))}}}",
        rf"\newcommand{{\ExperimentPValue}}{{{_pvalue(_get(results, 'experiment.p_value'))}}}",
        rf"\newcommand{{\ExperimentMDE}}{{{_tex(_pp(_get(results, 'experiment.mde'), 2))}}}",
        rf"\newcommand{{\CampaignDiD}}{{{_tex(_pp(_get(results, 'causal.did_effect'), 2))}}}",
        rf"\newcommand{{\CampaignIPTW}}{{{_tex(_pp(_get(results, 'causal.iptw_did_effect'), 2))}}}",
        rf"\newcommand{{\CampaignIPTWCI}}{{{_tex(_pp(_get(results, 'causal.iptw_ci_low'), 2))} to {_tex(_pp(_get(results, 'causal.iptw_ci_high'), 2))}}}",
        rf"\newcommand{{\CampaignSE}}{{{_tex(_num(_get(results, 'causal.iptw_standard_error'), 4))}}}",
        rf"\newcommand{{\CampaignESS}}{{{_tex(_integer(_get(results, 'causal.effective_sample_size')))}}}",
        rf"\newcommand{{\CampaignComparisonN}}{{{_tex(_integer(_get(results, 'causal.comparison_customers')))}}}",
        rf"\newcommand{{\CampaignTreatmentN}}{{{_tex(_integer(_get(results, 'causal.selected_region_customers')))}}}",
        rf"\newcommand{{\CommonSupport}}{{{_tex(_pct(support['value'], 1))}}}",
        rf"\newcommand{{\WeightedMaxSMD}}{{{_tex(_num(weighted_value, 5))}}}",
        rf"\newcommand{{\SelectedModel}}{{{_tex(_get(results, 'churn_model.selected_model').replace('_', ' '))}}}",
        rf"\newcommand{{\SelectionRule}}{{{_tex(_get(results, 'churn_model.selection_rule'))}}}",
        rf"\newcommand{{\ChurnAUC}}{{{_tex(_num(_get(results, 'churn_model.roc_auc'), 3))}}}",
        rf"\newcommand{{\ChurnLift}}{{{_tex(_num(_get(results, 'churn_model.lift_at_10pct'), 3))}}}",
        rf"\newcommand{{\ChurnCapture}}{{{_tex(_pct(_get(results, 'churn_model.capture_at_10pct'), 1))}}}",
        rf"\newcommand{{\ChurnEvaluationN}}{{{_tex(_integer(_get(results, 'churn_model.evaluation_customers')))}}}",
        rf"\newcommand{{\ChurnTopDecileN}}{{{_tex(_integer(_get(results, 'churn_model.top_decile_customers')))}}}",
        rf"\newcommand{{\ResponseAUC}}{{{_tex(_num(_get(results, 'response_propensity.roc_auc'), 3))}}}",
        rf"\newcommand{{\ResponseLift}}{{{_tex(_num(_get(results, 'response_propensity.lift_at_10pct'), 3))}}}",
        rf"\newcommand{{\ResponseCapture}}{{{_tex(_pct(_get(results, 'response_propensity.capture_at_10pct'), 1))}}}",
        rf"\newcommand{{\ResponseEvaluationN}}{{{_tex(_integer(_get(results, 'response_propensity.evaluation_customers')))}}}",
        rf"\newcommand{{\ResponseTopDecileN}}{{{_tex(_integer(_get(results, 'response_propensity.top_decile_customers')))}}}",
        rf"\newcommand{{\MaxPSI}}{{{_tex(_num(_get(results, 'monitoring.max_feature_psi'), 4))}}}",
        rf"\newcommand{{\BestStrategy}}{{{_tex(_get(results, 'economics.decision_summary.best_strategy').replace('_', ' '))}}}",
        rf"\newcommand{{\EvaluatedPopulation}}{{{_tex(_integer(_get(results, 'economics.decision_summary.evaluated_population')))}}}",
        rf"\newcommand{{\ExpectedNetValue}}{{{_tex(_num(_get(results, 'economics.decision_summary.expected_net_value'), 0))}}}",
        rf"\newcommand{{\TreatmentEffectAssumption}}{{{_tex(_pct(_get(results, 'economics.assumptions.treatment_effect_if_response'), 1))}}}",
        rf"\newcommand{{\ContactCost}}{{{_tex(_num(_get(results, 'economics.assumptions.contact_cost'), 2))}}}",
        rf"\newcommand{{\IncentiveCost}}{{{_tex(_num(_get(results, 'economics.assumptions.incentive_cost'), 2))}}}",
        rf"\newcommand{{\CapacityFraction}}{{{_tex(_pct(_get(results, 'economics.assumptions.capacity_fraction'), 0))}}}",
        rf"\newcommand{{\JourneyRows}}{{{_rows_tex(journey_rows)}}}",
        rf"\newcommand{{\ExperimentRows}}{{{_rows_tex(experiment_rows)}}}",
        rf"\newcommand{{\GuardrailRows}}{{{_rows_tex(guardrail_rows)}}}",
        rf"\newcommand{{\PretrendRows}}{{{_rows_tex(pretrend_rows)}}}",
        rf"\newcommand{{\ModelRows}}{{{_rows_tex(model_rows)}}}",
        rf"\newcommand{{\MonitoringRows}}{{{_rows_tex(monitoring_rows)}}}",
        rf"\newcommand{{\EconomicsRows}}{{{_rows_tex(economics_rows)}}}",
        rf"\newcommand{{\BankRows}}{{{_rows_tex(bank_rows)}}}",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = build(args.root.resolve(), args.output.resolve() if args.output else None)
    print(output.relative_to(args.root.resolve()))


if __name__ == "__main__":
    main()
