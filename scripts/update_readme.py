"""Refresh the README findings block from the canonical results manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- BEGIN GENERATED FINDINGS -->"
END = "<!-- END GENERATED FINDINGS -->"


def _get(results: dict[str, Any], path: str) -> Any:
    current: Any = results
    for key in path.split("."):
        current = current[key]
    return current


def _render(results: dict[str, Any]) -> str:
    customers = int(_get(results, "dataset.customers"))
    risk_difference = float(_get(results, "experiment.risk_difference")) * 100
    ci_low = float(_get(results, "experiment.ci_low")) * 100
    ci_high = float(_get(results, "experiment.ci_high")) * 100
    d7 = float(_get(results, "journey.mature_retention.d7")) * 100
    d30 = float(_get(results, "journey.mature_retention.d30")) * 100
    d60 = float(_get(results, "journey.mature_retention.d60")) * 100
    d90 = float(_get(results, "journey.mature_retention.d90")) * 100
    model = str(_get(results, "churn_model.selected_model")).replace("_", " ")
    auc = float(_get(results, "churn_model.roc_auc"))
    lift = float(_get(results, "churn_model.lift_at_10pct"))
    did = float(_get(results, "causal.did_effect")) * 100
    iptw = float(_get(results, "causal.iptw_did_effect")) * 100
    contacts = int(_get(results, "economics.decision_summary.customers_contacted"))
    net_value = float(_get(results, "economics.decision_summary.expected_net_value"))
    return f"""{START}
<!-- Generated from artifacts/results.json by scripts/update_readme.py. -->
The frozen full run contains {customers:,} synthetic customers covering {_get(results, "dataset.date_start")} through {_get(results, "dataset.date_end")}.

- The randomized intervention increases first-week activation by {risk_difference:.2f} percentage points. The recorded 95% confidence interval is +{ci_low:.2f} to +{ci_high:.2f} percentage points for eligible customers.
- Mature-cohort retention declines from {d7:.1f}% at D7 to {d30:.1f}% at D30, {d60:.1f}% at D60, and {d90:.1f}% at D90.
- The selected churn model is a {model} model. It records ROC AUC {auc:.3f} and top-decile lift {lift:.3f} on a later temporal holdout. This is a modest predictive association, not a causal treatment-benefit estimate.
- The observational campaign estimate is a {did:.2f} percentage-point unweighted DiD effect and a {iptw:.2f} percentage-point IPTW DiD effect. Its normal-approximation standard error ignores within-customer correlation.
- Every positive-contact strategy has negative expected net value under the fictional assumptions in [`config/economics.yml`](config/economics.yml). The expected-value strategy contacts {contacts:,} customers and records {net_value:,.0f} expected net value.

The decision is therefore narrow: keep the activation intervention behind a controlled experiment, and do not launch a positive-contact campaign under these assumptions. A rollout still requires incremental-value evidence, guardrail monitoring, and refreshed unit economics.
{END}"""


def update(readme_path: Path, results_path: Path) -> None:
    text = readme_path.read_text(encoding="utf-8")
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError("README must contain one generated findings marker pair")
    results = json.loads(results_path.read_text(encoding="utf-8"))
    prefix, remainder = text.split(START, 1)
    _, suffix = remainder.split(END, 1)
    readme_path.write_text(prefix + _render(results) + suffix, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readme", type=Path, default=ROOT / "README.md")
    parser.add_argument("--results", type=Path, default=ROOT / "artifacts" / "results.json")
    args = parser.parse_args()
    update(args.readme, args.results)


if __name__ == "__main__":
    main()
