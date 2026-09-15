import csv
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_latex_inputs import build


def _macro(name: str, value: str) -> str:
    return rf"\newcommand{{\{name}}}{{{value}}}"


def _escaped_pct(value: float, digits: int) -> str:
    return f"{value * 100:.{digits}f}\\%"


def _copy_report_inputs(destination: Path) -> Path:
    project = destination / "project"
    (project / "artifacts").mkdir(parents=True)
    (project / "config").mkdir()
    shutil.copy2(ROOT / "artifacts/results.json", project / "artifacts/results.json")
    shutil.copytree(ROOT / "artifacts/tables", project / "artifacts/tables")
    for name in ("external_benchmarks.yml", "economics.yml"):
        shutil.copy2(ROOT / "config" / name, project / "config" / name)
    return project


def _rewrite_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_latex_inputs_use_verified_current_denominators(tmp_path: Path) -> None:
    output = build(ROOT, tmp_path / "pulse_case_study_inputs.tex")
    text = output.read_text(encoding="utf-8")

    results = json.loads((ROOT / "artifacts/results.json").read_text(encoding="utf-8"))
    with (ROOT / "artifacts/tables/experiment_summary.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        experiment = {row["arm"]: row for row in csv.DictReader(handle)}
    with (ROOT / "artifacts/tables/campaign_iptw_balance.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        weighted_smd = max(
            abs(float(row["standardized_mean_difference"]))
            for row in csv.DictReader(handle)
            if row["weighting"] == "stabilized_iptw"
        )

    sustained = results["journey"]["sequential_sustained_engagement_d30"]
    overall = results["journey"]["d30_retention"]
    control_n = int(experiment["control"]["customers"])
    treatment_n = int(experiment["treatment"]["customers"])

    assert sustained != overall
    assert control_n != treatment_n
    assert _macro("SustainedDThirty", _escaped_pct(sustained, 3)) in text
    assert _macro("OverallDThirty", _escaped_pct(overall, 3)) in text
    assert _macro("ControlN", f"{control_n:,}") in text
    assert _macro("TreatmentN", f"{treatment_n:,}") in text
    assert (
        _macro("ChurnEvaluationN", f"{int(results['churn_model']['evaluation_customers']):,}")
        in text
    )
    assert (
        _macro(
            "ResponseEvaluationN",
            f"{int(results['response_propensity']['evaluation_customers']):,}",
        )
        in text
    )
    assert _macro("WeightedMaxSMD", f"{weighted_smd:.5f}") in text
    if results["experiment"]["p_value"] < 0.001:
        assert _macro("ExperimentPValue", "$p < 0.001$") in text


def test_latex_inputs_reject_cross_artifact_metric_mismatch(tmp_path: Path) -> None:
    project = _copy_report_inputs(tmp_path)

    experiment_path = project / "artifacts/tables/experiment_summary.csv"
    with experiment_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    next(row for row in rows if row["arm"] == "treatment")["activation_rate"] = "0.1"
    _rewrite_csv(experiment_path, rows)

    with pytest.raises(ValueError, match="treatment activation rate"):
        build(project, project / "reports/pulse_case_study_inputs.tex")


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("retention", "mature D7 retention"),
        ("mde", "experiment MDE"),
        ("economics_result", "economics assumption contact_cost"),
        ("economics_table", "economics profitability flag"),
    ],
)
def test_latex_inputs_reject_remaining_report_metric_mismatches(
    tmp_path: Path, case: str, message: str
) -> None:
    project = _copy_report_inputs(tmp_path)
    results_path = project / "artifacts/results.json"

    if case in {"retention", "economics_result"}:
        results = json.loads(results_path.read_text(encoding="utf-8"))
        if case == "retention":
            results["journey"]["mature_retention"]["d7"] = 0.9
        else:
            results["economics"]["assumptions"]["contact_cost"] = 99
        results_path.write_text(json.dumps(results), encoding="utf-8")
    else:
        table_name = "rct_guardrails.csv" if case == "mde" else "targeting_strategy_comparison.csv"
        table_path = project / "artifacts/tables" / table_name
        with table_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if case == "mde":
            next(row for row in rows if row["guardrail"] == "minimum_detectable_effect")[
                "value"
            ] = "0.9"
        else:
            next(row for row in rows if row["strategy"] == "expected_value")[
                "expected_net_value"
            ] = "999"
        _rewrite_csv(table_path, rows)

    with pytest.raises(ValueError, match=message):
        build(project, project / "reports/pulse_case_study_inputs.tex")
