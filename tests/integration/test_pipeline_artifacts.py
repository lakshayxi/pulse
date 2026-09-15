import json

from pulse.pipeline import run_pipeline


def test_ci_pipeline_writes_canonical_manifest(tmp_path) -> None:
    results = run_pipeline(
        profile="ci", data_dir=tmp_path / "data", artifact_dir=tmp_path / "artifacts"
    )
    manifest = tmp_path / "artifacts" / "results.json"
    assert manifest.exists()
    loaded = json.loads(manifest.read_text())
    assert loaded["dataset"]["synthetic"] is True
    assert loaded["churn_model"]["lift_at_10pct"] >= 0
    assert results["experiment"]["primary_metric"] == "first_week_activation"
    assert loaded["monitoring"]["performance_table"] == "monitoring_performance.csv"
    assert loaded["monitoring"]["performance_figure"] == "model_performance_over_time.svg"
    assert loaded["monitoring"]["evidence"]["holdout_months"] >= 1
    assert loaded["economics"]["decision_summary"]["best_strategy"] in {
        "contact_all",
        "risk",
        "value",
        "response",
        "expected_value",
    }
    decision = loaded["economics"]["decision_summary"]
    assert decision["customers_contacted"] >= 0
    assert (
        decision["contact_rate"]
        == decision["customers_contacted"] / decision["evaluated_population"]
    )
    assert decision["expected_net_value_per_10k"] == (
        decision["expected_net_value"] / decision["evaluated_population"] * 10_000
    )
    import pandas as pd

    performance = pd.read_csv(tmp_path / "artifacts" / "tables" / "monitoring_performance.csv")
    assert {"time_bucket", "base_rate", "roc_auc", "brier", "lift_at_10pct"}.issubset(
        performance.columns
    )
