"""Build and execute the small, evidence-linked Pulse working notebooks.

The notebooks are deliberately generated from one deterministic specification so
that they remain short, reproducible, and consistent with the pipeline output.
Run from the repository root with ``.venv/bin/python scripts/build_notebooks.py``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = ROOT / "notebooks"


COMMON = """from pathlib import Path
import json
import pandas as pd
from IPython.display import Image, display

ROOT = Path.cwd()
ARTIFACTS = ROOT / "artifacts"
with (ARTIFACTS / "results.json").open() as handle:
    results = json.load(handle)

def table(name, n=8):
    frame = pd.read_csv(ARTIFACTS / "tables" / name)
    display(frame.head(n))
    return frame

def figure(name):
    png = ARTIFACTS / "figures" / f"{name}.png"
    svg = ARTIFACTS / "figures" / f"{name}.svg"
    assert png.exists() and svg.exists(), f"missing paired figure outputs for {name}"
    assert "<svg" in svg.read_text(encoding="utf-8")[:1000]
    display(Image(filename=str(png), width=640))
    return png, svg
"""


SPECS: dict[str, dict[str, object]] = {
    "01_customer_journey": {
        "title": "Customer journey: where does activation break?",
        "question": "Business question: which sequential journey step is the clearest product opportunity, and what is the denominator for each decision?",
        "codes": [
            COMMON,
            "journey = table('journey.csv')\nfigure('journey_funnel')\nprint(results['journey'])",
            "early_stages = ['onboarding_completed', 'account_funded', 'first_transaction_7d']\nearly = journey.loc[journey['stage'].isin(early_stages)].copy()\nweakest = early.loc[early['conversion_from_previous'].astype(float).idxmin()]\nprint(f\"Evidence: the weakest early previous-stage conversion is {weakest['stage']!r} at {float(weakest['conversion_from_previous']):.1%}; the table preserves its denominator and scope.\")\nprint('Decision: prioritise the weakest early conversion, then validate the product intervention with a controlled experiment.')",
        ],
        "notes": "Uncertainty: this is synthetic, descriptive funnel evidence; it does not identify why customers drop or prove that an intervention will work.",
    },
    "02_cohorts": {
        "title": "Cohorts: is retention stable across signup months?",
        "question": "Business question: do retention patterns vary by signup cohort, and which windows are mature enough to compare?",
        "codes": [
            COMMON,
            "cohorts = table('retention_cohorts.csv', n=12)\nfigure('cohort_retention')\nprint(results['journey']['retention_windows'])",
            "mature = cohorts.dropna(subset=['retention']).copy()\nlatest = mature.sort_values(['horizon_days', 'cohort_month']).groupby('horizon_days').tail(1)\nprint('Evidence: maturity is encoded by horizon windows and analysis_end in the generated table.')\ndisplay(latest[['cohort_month', 'horizon_days', 'retention', 'cohort_size']])\nprint('Decision: use mature cohort comparisons to choose retention follow-up; treat recent cohorts as not-yet-observable rather than inactive.')",
        ],
        "notes": "Uncertainty: cohort retention is observational and synthetic; seasonality, composition, and incomplete windows can confound comparisons.",
    },
    "03_experiment": {
        "title": "Experiment: does the treatment move activation?",
        "question": "Business question: what is the estimated treatment effect, and did allocation and guardrails support a credible read?",
        "codes": [
            COMMON,
            "summary = table('experiment_summary.csv')\nguardrails = table('rct_guardrails.csv', n=12)\nfigure('rct_effect_ci')\nprint(results['experiment'])",
            "print('Evidence: the estimate and interval come from results.json; assignment quality and operational checks come from rct_guardrails.csv.')\nprint('Decision: ship only if the primary metric and guardrails meet the pre-specified decision rule; otherwise iterate or rerun.')",
        ],
        "notes": "Uncertainty: confidence intervals quantify sampling uncertainty under the experiment model; synthetic data and the stated guardrails limit external validity.",
    },
    "04_causal_analysis": {
        "title": "Causal analysis: what can the campaign data support?",
        "question": "Business question: is there evidence for an incremental campaign effect, and where do observational assumptions remain unverified?",
        "codes": [
            COMMON,
            "pretrend = table('campaign_pretrend.csv', n=12)\nbalance = table('campaign_iptw_balance.csv', n=12)\noverlap = table('campaign_overlap.csv', n=12)\nfigure('campaign_weekly_trends')\nprint(results['causal'])",
            "print('Evidence: pre-trends, balance, and overlap are diagnostics; results.json records the 2x2 contrast.')\nprint('Decision: use this as a diagnostic signal and design input, not as a standalone causal claim. Confirm assignment and parallel-trend assumptions before acting.')",
        ],
        "notes": "Uncertainty: the campaign is observational. Weighting diagnostics do not by themselves establish exchangeability, correct specification, or a causal effect.",
    },
    "05_churn": {
        "title": "Churn model: can risk ranking support intervention?",
        "question": "Business question: which model ranks future inactivity usefully, and how much of the event burden is captured in a constrained top-decile list?",
        "codes": [
            COMMON,
            "comparison = table('churn_model_comparison.csv', n=12)\nlift = table('churn_lift.csv', n=12)\ncalibration = table('churn_calibration.csv', n=12)\nfigure('churn_model_comparison')\nfigure('churn_lift')\nfigure('churn_calibration')\nprint(results['churn_model'])",
            "selected = results['churn_model']['selected_model']\nrow = comparison.loc[comparison['model'].eq(selected)].iloc[0]\nprint(f\"Evidence: selected model={selected!r}; top-decile lift={row['lift_at_10pct']:.3f}; capture={row['capture_at_10pct']:.3f}.\")\nprint('Decision: use the ranking for capacity-aware outreach only after checking calibration, drift, and intervention economics.')",
        ],
        "notes": "Uncertainty: predictive ranking is not a treatment effect. Performance is evaluation-sample evidence and may drift when customer behaviour or policy changes.",
    },
    "06_targeting": {
        "title": "Targeting: does intervention economics justify contact?",
        "question": "Business question: under explicit effect, response, value, and cost assumptions, which targeting strategy has positive expected value?",
        "codes": [
            COMMON,
            "strategies = table('targeting_strategy_comparison.csv', n=12)\nsensitivity = table('economics_sensitivity.csv', n=12)\nfigure('targeting_strategy_value')\nprint(results['economics'])",
            "best = strategies.sort_values('expected_net_value', ascending=False).iloc[0]\nprint(f\"Evidence: the highest expected net value strategy is {best['strategy']!r}; profitability is recorded in the generated comparison.\")\nprint('Decision: contact only where expected value remains positive across a decision-relevant sensitivity range, then validate with an experiment.')",
        ],
        "notes": "Uncertainty: expected value is assumption-driven and response propensity is predictive. It is not evidence that contacted customers will realise the assumed incremental effect.",
    },
}


def make_notebook(spec: dict[str, object]) -> nbf.NotebookNode:
    notebook = nbf.v4.new_notebook()
    notebook.metadata.kernelspec = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    notebook.metadata.language_info = {"name": "python", "pygments_lexer": "ipython3"}
    notebook.cells = [
        nbf.v4.new_markdown_cell(f"# {spec['title']}\n\n{spec['question']}"),
        *[nbf.v4.new_code_cell(code) for code in spec["codes"]],
        nbf.v4.new_markdown_cell(
            f"**Uncertainty and scope.** {spec['notes']}\n\n"
            "**Decision framing.** Treat the generated artifacts as an auditable working read: inspect the source table, check assumptions, and validate the proposed action with an appropriate follow-up measurement."
        ),
    ]
    return notebook


def build() -> list[Path]:
    NOTEBOOK_DIR.mkdir(exist_ok=True)
    paths = []
    for stem, spec in SPECS.items():
        path = NOTEBOOK_DIR / f"{stem}.ipynb"
        with path.open("w", encoding="utf-8") as handle:
            nbf.write(make_notebook(spec), handle)
        paths.append(path)
    return paths


def execute(paths: list[Path]) -> None:
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            notebook = nbf.read(handle, as_version=4)
        client = NotebookClient(
            notebook,
            timeout=120,
            kernel_name="python3",
            resources={"metadata": {"path": str(ROOT)}},
        )
        client.execute()
        with path.open("w", encoding="utf-8") as handle:
            nbf.write(notebook, handle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-only", action="store_true", help="write notebooks without executing them"
    )
    args = parser.parse_args()
    paths = build()
    if not args.build_only:
        execute(paths)
    print("\n".join(str(path.relative_to(ROOT)) for path in paths))


if __name__ == "__main__":
    main()
