"""Build the recruiter-facing Pulse case-study PDF from frozen artifacts.

The generator reads the results manifest, generated tables, and PNG figures at
runtime. It does not recompute analysis or embed a second copy of the results.
Run it from the repository root with ``python -m pulse.reporting.build_report``.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PAGE_WIDTH, PAGE_HEIGHT = letter
INK = colors.HexColor("#132238")
BLUE = colors.HexColor("#3973AC")
TEAL = colors.HexColor("#2C8C88")
ORANGE = colors.HexColor("#D48A3C")
MUTED = colors.HexColor("#728096")
PALE_BLUE = colors.HexColor("#EAF2F9")
PALE_TEAL = colors.HexColor("#E8F4F1")
PALE_ORANGE = colors.HexColor("#FBF0E3")
RULE = colors.HexColor("#D7DEE7")


@dataclass(frozen=True)
class Inputs:
    """Validated paths for one report build."""

    results_path: Path
    tables_dir: Path
    figures_dir: Path
    output_path: Path
    external_benchmarks_path: Path


REQUIRED_RESULTS = (
    "dataset.synthetic",
    "dataset.customers",
    "dataset.date_start",
    "dataset.date_end",
    "journey.activation_rate",
    "journey.d30_retention",
    "journey.activation_contract",
    "journey.mature_retention.d7",
    "journey.mature_retention.d30",
    "experiment.primary_metric",
    "experiment.control_rate",
    "experiment.treatment_rate",
    "experiment.risk_difference",
    "experiment.ci_low",
    "experiment.ci_high",
    "experiment.p_value",
    "experiment.eligible_per_arm",
    "experiment.claim_scope",
    "churn_model.selected_model",
    "churn_model.roc_auc",
    "churn_model.lift_at_10pct",
    "churn_model.claim_scope",
    "response_propensity.claim_scope",
    "causal.design",
    "causal.did_effect",
    "causal.iptw_did_effect",
    "causal.iptw_standard_error",
    "causal.iptw_ci_low",
    "causal.iptw_ci_high",
    "causal.uncertainty_method",
    "causal.effective_sample_size",
    "causal.claim_scope",
    "economics.assumptions.treatment_effect_if_response",
    "economics.assumptions.contact_cost",
    "economics.assumptions.incentive_cost",
    "economics.assumptions.capacity_fraction",
    "economics.decision_summary.best_strategy",
    "economics.decision_summary.customers_contacted",
    "economics.decision_summary.expected_net_value",
    "economics.claim_scope",
)

REQUIRED_TABLES = (
    "journey.csv",
    "retention_cohorts.csv",
    "experiment_summary.csv",
    "rct_guardrails.csv",
    "rct_balance.csv",
    "campaign_weekly_trends.csv",
    "campaign_pretrend.csv",
    "campaign_overlap.csv",
    "campaign_iptw_balance.csv",
    "churn_model_comparison.csv",
    "churn_lift.csv",
    "monitoring_performance.csv",
    "targeting_strategy_comparison.csv",
    "economics_sensitivity.csv",
)

REQUIRED_FIGURES = (
    "journey_funnel.png",
    "cohort_retention.png",
    "rct_effect_ci.png",
    "campaign_weekly_trends.png",
    "churn_model_comparison.png",
    "churn_lift.png",
    "targeting_strategy_value.png",
    "model_performance_over_time.png",
)


def _get(mapping: dict[str, Any], path: str) -> Any:
    """Get one dotted result value and fail with an actionable message."""

    current: Any = mapping
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"results.json is missing required key: {path}")
        current = current[key]
    return current


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"required table is missing: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"required table is empty: {path}")
    return rows


def validate_inputs(inputs: Inputs) -> dict[str, Any]:
    """Validate all report inputs before authoring any PDF pages."""

    if not inputs.results_path.is_file():
        raise ValueError(f"results manifest is missing: {inputs.results_path}")
    try:
        results = json.loads(inputs.results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"results manifest is not valid JSON: {inputs.results_path}") from exc
    if not isinstance(results, dict):
        raise TypeError("results manifest must contain a JSON object")
    for path in REQUIRED_RESULTS:
        _get(results, path)
    for name in REQUIRED_TABLES:
        _read_csv(inputs.tables_dir / name)
    for name in REQUIRED_FIGURES:
        figure = inputs.figures_dir / name
        if not figure.is_file():
            raise ValueError(f"required PNG figure is missing: {figure}")
    _load_external_benchmarks(inputs.external_benchmarks_path)
    return results


def _number(value: Any, digits: int = 2) -> str:
    return f"{float(value):,.{digits}f}"


def _p_value(value: Any) -> str:
    """Format a p-value without implying precision below the report threshold."""

    numeric = float(value)
    return "<0.001" if numeric < 0.001 else _number(numeric, 3)


def _integer(value: Any) -> str:
    return f"{round(float(value)):,.0f}"


def _pct(value: Any, digits: int = 1) -> str:
    return f"{float(value) * 100:.{digits}f}%"


def _pp(value: Any, digits: int = 2) -> str:
    return f"{float(value) * 100:+.{digits}f} pp"


def _money(value: Any, digits: int = 0) -> str:
    return f"{float(value):+,.{digits}f} fictional units"


def _text(value: Any) -> str:
    return str(value).replace("_", " ")


def _source_reference(benchmark: dict[str, Any]) -> str:
    """Format paginated and web-only evidence references cleanly."""

    page = str(benchmark["page"])
    locator = (
        page if page.lower() == "web page" or page.lower().startswith("slide ") else f"p. {page}"
    )
    return f"{benchmark['source']}, {locator}"


def _load_rows(inputs: Inputs, name: str) -> list[dict[str, str]]:
    return _read_csv(inputs.tables_dir / name)


def _load_external_benchmarks(path: Path) -> dict[str, Any]:
    """Load and validate the source registry used by the calibration page."""

    if not path.is_file():
        raise ValueError(f"external benchmark registry is missing: {path}")
    try:
        registry = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"external benchmark registry is not valid YAML: {path}") from exc
    if not isinstance(registry, dict) or not isinstance(registry.get("benchmarks"), list):
        raise TypeError("external benchmark registry must contain a benchmarks list")
    required_fields = {"bank", "period", "evidence", "implication", "source", "page", "url"}
    for index, benchmark in enumerate(registry["benchmarks"]):
        if not isinstance(benchmark, dict) or not required_fields.issubset(benchmark):
            raise ValueError(f"external benchmark entry {index} is missing required fields")
    return registry


def _style_sheet() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=32,
            textColor=INK,
            spaceAfter=12,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=17,
            textColor=MUTED,
            spaceAfter=12,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=19,
            leading=23,
            textColor=INK,
            spaceAfter=6,
        ),
        "kicker": ParagraphStyle(
            "Kicker",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=TEAL,
            uppercase=True,
            spaceAfter=3,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=INK,
            spaceBefore=4,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=13,
            textColor=INK,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.6,
            leading=10,
            textColor=MUTED,
            spaceAfter=3,
        ),
        "table": ParagraphStyle(
            "Table",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.1,
            leading=8.4,
            textColor=INK,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.1,
            leading=8.4,
            textColor=colors.white,
        ),
        "callout": ParagraphStyle(
            "Callout",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=INK,
            spaceAfter=2,
        ),
        "metric": ParagraphStyle(
            "Metric",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=19,
            textColor=INK,
            alignment=TA_CENTER,
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.4,
            leading=9,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
    }


def _p(text: str, styles: dict[str, ParagraphStyle], style: str = "body") -> Paragraph:
    return Paragraph(text, styles[style])


def _table(
    headers: list[str],
    rows: Iterable[Iterable[Any]],
    styles: dict[str, ParagraphStyle],
    widths: list[float] | None = None,
    font_size: float = 7.1,
) -> Table:
    data = [[_p(header, styles, "table_header") for header in headers]]
    data.extend([[_p(str(value), styles, "table") for value in row] for row in rows])
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.3, RULE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8FA")]),
            ]
        )
    )
    return table


def _figure(path: Path, width: float, height: float) -> Image:
    """Scale a PNG into a bounded report slot while preserving its aspect ratio."""

    source_width, source_height = ImageReader(str(path)).getSize()
    scale = min(width / source_width, height / source_height)
    image = Image(str(path), width=source_width * scale, height=source_height * scale)
    image.hAlign = "CENTER"
    return image


def _metric_cards(
    cards: list[tuple[str, str, colors.Color]], styles: dict[str, ParagraphStyle]
) -> Table:
    cells = []
    for value, label, background in cards:
        cells.append(
            Table(
                [[_p(value, styles, "metric")], [_p(label, styles, "metric_label")]],
                colWidths=1.97 * inch,
                rowHeights=[0.34 * inch, 0.35 * inch],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), background),
                        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ]
                ),
            )
        )
    return Table([cells], colWidths=[2.05 * inch] * len(cells), hAlign="LEFT")


def _callout(
    text: str, styles: dict[str, ParagraphStyle], background: colors.Color = PALE_TEAL
) -> Table:
    return Table(
        [[_p(text, styles, "callout")]],
        colWidths=[7.1 * inch],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.6, TEAL),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        ),
    )


def _header_footer(canvas: Any, doc: Any) -> None:
    canvas.saveState()
    page = canvas.getPageNumber()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(
        0.7 * inch, PAGE_HEIGHT - 0.48 * inch, PAGE_WIDTH - 0.7 * inch, PAGE_HEIGHT - 0.48 * inch
    )
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.setFillColor(INK)
    canvas.drawString(
        0.7 * inch, PAGE_HEIGHT - 0.35 * inch, "PULSE / CUSTOMER ANALYTICS CASE STUDY"
    )
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(PAGE_WIDTH - 0.7 * inch, 0.38 * inch, f"{page:02d}")
    canvas.drawString(0.7 * inch, 0.38 * inch, "Synthetic evidence; see limitations")
    canvas.restoreState()


def _section(story: list[Any], styles: dict[str, ParagraphStyle], kicker: str, title: str) -> None:
    story.extend(
        [_p(kicker, styles, "kicker"), _p(title, styles, "section"), Spacer(1, 0.05 * inch)]
    )


def _fmt_rows(
    rows: list[dict[str, str]], columns: list[tuple[str, str, Callable[[str], str]]]
) -> list[list[str]]:
    return [[formatter(row[key]) for key, _, formatter in columns] for row in rows]


def _report_story(results: dict[str, Any], inputs: Inputs) -> list[Any]:
    styles = _style_sheet()
    story: list[Any] = []
    journey = _load_rows(inputs, "journey.csv")
    external_benchmarks = _load_external_benchmarks(inputs.external_benchmarks_path)
    experiment = _load_rows(inputs, "experiment_summary.csv")
    guardrails = _load_rows(inputs, "rct_guardrails.csv")
    pretrend = _load_rows(inputs, "campaign_pretrend.csv")
    overlap = _load_rows(inputs, "campaign_overlap.csv")
    model_comparison = _load_rows(inputs, "churn_model_comparison.csv")
    monitoring = _load_rows(inputs, "monitoring_performance.csv")
    strategy = _load_rows(inputs, "targeting_strategy_comparison.csv")

    figure = lambda name: inputs.figures_dir / name

    # Page 1: executive summary.
    story.extend(
        [
            Spacer(1, 0.35 * inch),
            _p("PULSE", styles, "kicker"),
            _p("From customer journey to\ncommercial decision", styles, "title"),
            _p(
                "A reproducible digital-banking analytics case study that joins a synthetic event warehouse, randomized experiment, observational diagnostics, predictive modelling, and unit economics.",
                styles,
                "subtitle",
            ),
            Spacer(1, 0.12 * inch),
            _callout(
                "Decision: keep the activation intervention as a measured experiment. Do not launch a positive-contact campaign under the supplied fictional economics.",
                styles,
            ),
            Spacer(1, 0.17 * inch),
            _metric_cards(
                [
                    (
                        _pp(_get(results, "experiment.risk_difference")),
                        "RCT activation effect",
                        PALE_TEAL,
                    ),
                    (_pct(_get(results, "journey.d30_retention")), "D30 retention", PALE_BLUE),
                    (
                        _money(_get(results, "economics.decision_summary.expected_net_value")),
                        "Expected-value policy",
                        PALE_ORANGE,
                    ),
                ],
                styles,
            ),
            Spacer(1, 0.2 * inch),
            _p(
                f"The full run covers {_integer(_get(results, 'dataset.customers'))} synthetic customers from {_get(results, 'dataset.date_start')} through {_get(results, 'dataset.date_end')}. The activation estimate is randomized; the campaign estimate is observational; the churn and response scores are predictive associations.",
                styles,
            ),
            _p(
                "The commercial conclusion is intentionally stricter than the statistical conclusion. A clear treatment effect does not imply a profitable broad campaign.",
                styles,
            ),
            PageBreak(),
        ]
    )

    # Page 2: context and metric contract.
    _section(story, styles, "01 / CONTEXT", "One metric contract across the journey")
    story.extend(
        [
            _p(
                "Pulse treats the customer journey as a sequence of measurable decisions. The same definitions feed the simulation, warehouse, SQL checks, notebooks, and report. This avoids presenting a funnel assembled from incompatible denominators.",
                styles,
            ),
            _p("Scope", styles, "h2"),
            _table(
                ["Item", "Recorded value"],
                [
                    [
                        "Population",
                        f"{_integer(_get(results, 'dataset.customers'))} synthetic customers",
                    ],
                    [
                        "Coverage",
                        f"{_get(results, 'dataset.date_start')} to {_get(results, 'dataset.date_end')}",
                    ],
                    ["Activation", _get(results, "journey.activation_contract")],
                    [
                        "Retention windows",
                        "; ".join(
                            f"{key.upper()} = {_get(results, f'journey.retention_windows.{key}')}"
                            for key in ("d7", "d30", "d60", "d90")
                        ),
                    ],
                ],
                styles,
                widths=[1.3 * inch, 5.8 * inch],
            ),
            Spacer(1, 0.13 * inch),
            _p("The canonical journey", styles, "h2"),
            _figure(figure("journey_funnel.png"), 6.7 * inch, 3.0 * inch),
            Spacer(1, 0.04 * inch),
            _p(
                f"The funnel ends with {_integer(next(row['customers'] for row in journey if row['stage'] == 'sustained_engagement_d30'))} customers at sustained D30 engagement, or {_pct(_get(results, 'journey.d30_retention'))} of signups.",
                styles,
                "small",
            ),
            PageBreak(),
        ]
    )

    # Page 3: journey and cohorts.
    sequential_journey = [row for row in journey if row["metric_scope"] == "sequential_funnel"]
    early_activation_stages = {
        "onboarding_completed",
        "account_funded",
        "first_transaction_7d",
    }
    early_activation = [
        row for row in sequential_journey if row["stage"] in early_activation_stages
    ]
    weakest_early_conversion = min(
        early_activation, key=lambda row: float(row["conversion_from_previous"])
    )
    weakest_stage = _text(weakest_early_conversion["stage"])
    weakest_rate = _pct(weakest_early_conversion["conversion_from_previous"])
    _section(
        story,
        styles,
        "02 / JOURNEY",
        f"Activation opportunity: {weakest_stage} has the weakest early conversion",
    )
    story.extend(
        [
            _p(
                f"Among onboarding, funding, and first-transaction stages, {weakest_stage} has the weakest previous-stage conversion at {weakest_rate}. Funding is necessary but insufficient: the operational question is how to convert funded customers into a first meaningful transaction, then sustain activity beyond the first week.",
                styles,
            ),
            _table(
                ["Stage", "Customers", "Signup conversion", "Previous-stage conversion"],
                _fmt_rows(
                    sequential_journey,
                    [
                        ("stage", "Stage", _text),
                        ("customers", "Customers", _integer),
                        ("conversion_from_signup", "Signup conversion", lambda value: _pct(value)),
                        (
                            "conversion_from_previous",
                            "Previous-stage conversion",
                            lambda value: _pct(value),
                        ),
                    ],
                ),
                styles,
                widths=[1.6 * inch, 1.1 * inch, 1.5 * inch, 1.7 * inch],
            ),
            Spacer(1, 0.15 * inch),
            _p("Cohort view", styles, "h2"),
            _figure(figure("cohort_retention.png"), 6.7 * inch, 3.25 * inch),
            Spacer(1, 0.05 * inch),
            _p(
                f"Mature-cohort retention is {_pct(_get(results, 'journey.mature_retention.d7'))} at D7 and {_pct(_get(results, 'journey.mature_retention.d30'))} at D30. The cohort table records the observation cutoff and window for each estimate.",
                styles,
                "small",
            ),
            PageBreak(),
        ]
    )

    # Page 4: experiment design.
    _section(
        story, styles, "03 / EXPERIMENT", "A pre-outcome assignment creates a clean decision test"
    )
    story.extend(
        [
            _p(
                "The randomized experiment asks whether an onboarding nudge or incentive increases D7 activation among customers funded by signup day 3 who had not activated at eligibility. The primary estimate is intent-to-treat.",
                styles,
            ),
            _table(
                ["Design element", "Evidence in the frozen run"],
                [
                    ["Primary metric", _get(results, "experiment.primary_metric")],
                    ["Allocation", "Expected 50:50 treatment and control allocation"],
                    [
                        "Eligible customers per arm",
                        _integer(_get(results, "experiment.eligible_per_arm")),
                    ],
                    ["Claim scope", _get(results, "experiment.claim_scope")],
                    [
                        "Guardrails",
                        "Assignment ratio, balance, support contacts, failed payments, and incentive cost",
                    ],
                ],
                styles,
                widths=[1.65 * inch, 5.45 * inch],
            ),
            Spacer(1, 0.15 * inch),
            _p("Guardrails", styles, "h2"),
            _table(
                ["Guardrail", "Value", "Threshold", "Status"],
                [
                    [
                        row["guardrail"],
                        _number(row["value"]),
                        _number(row["threshold"]),
                        row["status"],
                    ]
                    for row in guardrails
                    if row["guardrail"] != "minimum_detectable_effect"
                ],
                styles,
                widths=[2.25 * inch, 1.35 * inch, 1.35 * inch, 1.1 * inch],
            ),
            Spacer(1, 0.13 * inch),
            _p(
                "The balance table remains visible as an audit artifact. The report uses it to support experiment integrity, not to replace the outcome estimate.",
                styles,
            ),
            PageBreak(),
        ]
    )

    # Page 5: RCT result.
    _section(story, styles, "04 / RCT RESULT", "Activation responds; economics still decide")
    story.extend(
        [
            _figure(figure("rct_effect_ci.png"), 6.7 * inch, 2.65 * inch),
            Spacer(1, 0.06 * inch),
            _table(
                ["Arm", "Customers", "Activations", "D7 activation", "D30 retention"],
                _fmt_rows(
                    experiment,
                    [
                        ("arm", "Arm", _text),
                        ("customers", "Customers", _integer),
                        ("activations", "Activations", _integer),
                        ("activation_rate", "D7 activation", _pct),
                        ("d30_rate", "D30 retention", _pct),
                    ],
                ),
                styles,
                widths=[1.05 * inch, 1.15 * inch, 1.15 * inch, 1.35 * inch, 1.35 * inch],
            ),
            Spacer(1, 0.16 * inch),
            _metric_cards(
                [
                    (
                        _pp(_get(results, "experiment.risk_difference")),
                        "Treatment minus control",
                        PALE_TEAL,
                    ),
                    (
                        f"{_pp(_get(results, 'experiment.ci_low'))} to {_pp(_get(results, 'experiment.ci_high'))}",
                        "95% confidence interval",
                        PALE_BLUE,
                    ),
                    (
                        _p_value(_get(results, "experiment.p_value")),
                        "p-value",
                        PALE_ORANGE,
                    ),
                ],
                styles,
            ),
            Spacer(1, 0.14 * inch),
            _callout(
                "Interpretation: the intervention has a positive randomized activation effect. This supports continued controlled testing, not automatic rollout.",
                styles,
            ),
            PageBreak(),
        ]
    )

    # Page 6: behavioural/product evidence.
    _section(
        story,
        styles,
        "05 / BEHAVIOURAL EVIDENCE",
        "The selected-region campaign changes the observed activity pattern",
    )
    story.extend(
        [
            _p(
                "The weekly trend shows a higher post-campaign activity rate in the selected region. Pre-period differences remain visible so that the reader can judge the design instead of seeing only one summary number.",
                styles,
            ),
            _figure(figure("campaign_weekly_trends.png"), 6.7 * inch, 3.45 * inch),
            Spacer(1, 0.07 * inch),
            _table(
                ["Relative week", "Comparison", "Selected", "Difference"],
                [
                    [
                        row["relative_week"],
                        _pct(row["0"], 2),
                        _pct(row["1"], 2),
                        _pp(row["treated_minus_control"], 2),
                    ]
                    for row in pretrend
                ],
                styles,
                widths=[1.15 * inch, 1.35 * inch, 1.35 * inch, 1.35 * inch],
            ),
            Spacer(1, 0.07 * inch),
            _p(
                "This evidence is useful for product diagnosis. It is not randomized evidence because treatment was selected by region.",
                styles,
                "small",
            ),
            PageBreak(),
        ]
    )

    # Page 7: observational causal analysis.
    _section(
        story,
        styles,
        "06 / OBSERVATIONAL CAUSAL ANALYSIS",
        "DiD and IPTW agree, with a narrower claim",
    )
    story.extend(
        [
            _p(
                "The campaign estimate combines difference-in-differences with stabilized inverse-probability-of-treatment weighting (IPTW) diagnostics. Weighting reduces measured imbalance, but it cannot make a selected-region campaign randomized.",
                styles,
            ),
            _table(
                ["Estimate", "Value", "Evidence boundary"],
                [
                    [
                        "Unweighted DiD",
                        _pp(_get(results, "causal.did_effect")),
                        "Observed region-by-time contrast",
                    ],
                    [
                        "IPTW DiD",
                        _pp(_get(results, "causal.iptw_did_effect")),
                        "Weighted customer-week means",
                    ],
                    [
                        "95% interval",
                        f"{_pp(_get(results, 'causal.iptw_ci_low'))} to {_pp(_get(results, 'causal.iptw_ci_high'))}",
                        "Normal approximation",
                    ],
                    [
                        "Standard error",
                        _number(_get(results, "causal.iptw_standard_error"), 4),
                        "Ignores within-customer correlation",
                    ],
                    [
                        "Effective sample size",
                        _integer(_get(results, "causal.effective_sample_size")),
                        "Recorded diagnostic",
                    ],
                ],
                styles,
                widths=[1.45 * inch, 1.45 * inch, 4.2 * inch],
            ),
            Spacer(1, 0.13 * inch),
            _p("Diagnostics", styles, "h2"),
            _table(
                ["Diagnostic", "Recorded value", "Threshold", "Status"],
                [
                    [
                        row["diagnostic"],
                        _number(row["value"]),
                        _number(row["threshold"]),
                        row["status"],
                    ]
                    for row in overlap
                    if row["diagnostic"] != "bin_count"
                ],
                styles,
                widths=[2.15 * inch, 1.45 * inch, 1.25 * inch, 1.0 * inch],
            ),
            Spacer(1, 0.1 * inch),
            _p(
                f"Claim scope: {_get(results, 'causal.claim_scope')} The reported uncertainty method {_get(results, 'causal.uncertainty_method').lower()}.",
                styles,
                "small",
            ),
            PageBreak(),
        ]
    )

    # Page 8: predictive modelling.
    _section(
        story, styles, "07 / PREDICTIVE MODELLING", "Useful ranking signal, modest discrimination"
    )
    story.extend(
        [
            _p(
                "The selected churn model is evaluated on a later temporal holdout. The output is a prioritization score, not a causal estimate of who will benefit from contact.",
                styles,
            ),
            _figure(figure("churn_model_comparison.png"), 3.25 * inch, 2.2 * inch),
            _figure(figure("churn_lift.png"), 3.25 * inch, 2.2 * inch),
            Spacer(1, 0.08 * inch),
            _table(
                ["Model", "Brier", "ROC AUC", "Lift at 10%", "Capture at 10%"],
                [
                    [
                        row["model"],
                        _number(row["brier"], 3),
                        _number(row["roc_auc"], 3),
                        _number(row["lift_at_10pct"], 3),
                        _pct(row["capture_at_10pct"], 1),
                    ]
                    for row in model_comparison
                ],
                styles,
                widths=[2.05 * inch, 0.85 * inch, 1.0 * inch, 1.15 * inch, 1.35 * inch],
            ),
            Spacer(1, 0.13 * inch),
            _callout(
                f"Selected model: {_text(_get(results, 'churn_model.selected_model'))}. ROC AUC {_number(_get(results, 'churn_model.roc_auc'), 3)} and top-decile lift {_number(_get(results, 'churn_model.lift_at_10pct'), 3)} are enough to support testing a rank-ordered queue, not enough to claim strong individual prediction.",
                styles,
                PALE_BLUE,
            ),
            PageBreak(),
        ]
    )

    # Page 9: economics.
    _section(
        story,
        styles,
        "08 / TARGETING AND ECONOMICS",
        "Every positive-contact strategy is value-negative",
    )
    story.extend(
        [
            _p(
                "The policy scores customers with churn risk, response propensity, and customer value. It then subtracts contact and incentive costs. These are fictional scenario assumptions, so the result is a decision screen rather than a production forecast.",
                styles,
            ),
            _table(
                ["Assumption", "Value"],
                [
                    [
                        "Treatment effect if response",
                        _number(
                            _get(results, "economics.assumptions.treatment_effect_if_response"), 2
                        ),
                    ],
                    [
                        "Contact cost",
                        _money(_get(results, "economics.assumptions.contact_cost"), 2),
                    ],
                    [
                        "Incentive cost",
                        _money(_get(results, "economics.assumptions.incentive_cost"), 2),
                    ],
                    [
                        "Capacity fraction",
                        _pct(_get(results, "economics.assumptions.capacity_fraction"), 0),
                    ],
                ],
                styles,
                widths=[3.2 * inch, 2.2 * inch],
            ),
            Spacer(1, 0.12 * inch),
            _figure(figure("targeting_strategy_value.png"), 6.7 * inch, 2.7 * inch),
            Spacer(1, 0.06 * inch),
            _table(
                ["Strategy", "Contacted", "Expected net value", "Profitable"],
                [
                    [
                        row["strategy"],
                        _integer(row["customers_contacted"]),
                        _money(row["expected_net_value"]),
                        row["profitable"],
                    ]
                    for row in strategy
                ],
                styles,
                widths=[1.8 * inch, 1.15 * inch, 1.9 * inch, 1.05 * inch],
            ),
            Spacer(1, 0.09 * inch),
            _callout(
                f"Expected-value strategy: {_integer(_get(results, 'economics.decision_summary.customers_contacted'))} customers contacted and {_money(_get(results, 'economics.decision_summary.expected_net_value'))} expected net value. The correct action under these assumptions is zero contact.",
                styles,
                PALE_ORANGE,
            ),
            PageBreak(),
        ]
    )

    # Page 10: directional external calibration.
    _section(
        story,
        styles,
        "09 / EXTERNAL CALIBRATION",
        "Indian-bank disclosures inform structure, not retention levels",
    )
    story.extend(
        [
            _p(
                "The synthetic lifecycle uses public Indian-bank disclosures as directional design evidence. These sources motivate multiple digital states, delayed activation, reactivation, product depth, and cohort-level shocks. The segment weights and shock sizes remain fictional inputs; they are not calibrated to reported bank metrics.",
                styles,
            ),
            _table(
                ["Bank", "Public evidence", "Synthetic design implication"],
                [
                    [
                        benchmark["bank"],
                        f"{benchmark['evidence']} ({_source_reference(benchmark)})",
                        benchmark["implication"],
                    ]
                    for benchmark in external_benchmarks["benchmarks"]
                ],
                styles,
                widths=[1.1 * inch, 3.65 * inch, 2.35 * inch],
            ),
            Spacer(1, 0.13 * inch),
            _callout(
                str(external_benchmarks["scope"]),
                styles,
                PALE_ORANGE,
            ),
            Spacer(1, 0.1 * inch),
            _p(
                "The reviewed disclosures use different denominators, including registered users, monthly active users, engagements, transaction share, and product adoption. None is a comparable signup-cohort D7/D30/D60/D90 retention benchmark for Pulse.",
                styles,
                "small",
            ),
            PageBreak(),
        ]
    )

    # Page 11: monitoring, recommendation, limitations.
    _section(
        story,
        styles,
        "10 / MONITORING AND HAND-OFF",
        "Ship the measurement loop before scaling contact",
    )
    story.extend(
        [
            _p(
                "The monitoring artifact tracks temporal performance and feature drift. It supports a repeatable review cadence if the model or intervention moves beyond this synthetic case study.",
                styles,
            ),
            _figure(figure("model_performance_over_time.png"), 6.7 * inch, 2.65 * inch),
            Spacer(1, 0.05 * inch),
            _table(
                [
                    "Holdout bucket",
                    "Customers",
                    "Base rate",
                    "ROC AUC",
                    "Lift at 10%",
                    "Calibration error",
                ],
                [
                    [
                        row["time_bucket"],
                        _integer(row["customers"]),
                        _pct(row["base_rate"], 1),
                        _number(row["roc_auc"], 3),
                        _number(row["lift_at_10pct"], 3),
                        _number(row["calibration_error"], 3),
                    ]
                    for row in monitoring
                ],
                styles,
                widths=[1.1 * inch, 0.9 * inch, 0.95 * inch, 0.85 * inch, 1.0 * inch, 1.25 * inch],
            ),
            Spacer(1, 0.11 * inch),
            _callout(
                "Recommendation: preserve the RCT as the decision gate, add incremental-value measurement before contact, and monitor performance, calibration, drift, complaints, and profitability by segment.",
                styles,
            ),
            Spacer(1, 0.08 * inch),
            _p("Limitations", styles, "h2"),
            _p(
                "All data are behaviourally plausible synthetic simulation. Observational associations are not causal claims. The IPTW standard error ignores within-customer correlation. Economic conclusions depend on fictional unit-economics assumptions. The churn and response models predict association, not treatment benefit.",
                styles,
            ),
            _p(
                "Reproduce the artifact with the repository pipeline, then run the report module against the generated artifacts. The PDF is a presentation layer over the manifest and tables; it does not replace their provenance.",
                styles,
                "small",
            ),
        ]
    )
    return story


def build_report(inputs: Inputs) -> None:
    """Validate inputs and write the report PDF."""

    results = validate_inputs(inputs)
    inputs.output_path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(inputs.output_path),
        pagesize=letter,
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.68 * inch,
        bottomMargin=0.62 * inch,
        title="Pulse customer analytics case study",
        author="Pulse",
        subject="Synthetic customer analytics and experimentation",
    )
    document.build(
        _report_story(results, inputs), onFirstPage=_header_footer, onLaterPages=_header_footer
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("artifacts/results.json"))
    parser.add_argument("--tables", type=Path, default=Path("artifacts/tables"))
    parser.add_argument("--figures", type=Path, default=Path("artifacts/figures"))
    parser.add_argument("--output", type=Path, default=Path("reports/pulse_case_study.pdf"))
    parser.add_argument(
        "--external-benchmarks",
        type=Path,
        default=Path("config/external_benchmarks.yml"),
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    build_report(
        Inputs(
            results_path=args.results,
            tables_dir=args.tables,
            figures_dir=args.figures,
            output_path=args.output,
            external_benchmarks_path=args.external_benchmarks,
        )
    )


if __name__ == "__main__":
    main()
