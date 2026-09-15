# Pulse architecture

Pulse is a reproducible decision-science project for a fictional digital bank. It follows one analytical path: acquisition, onboarding, activation, retention, intervention evaluation, risk/response scoring, and profitable targeting.

## Layers

1. **Simulation** creates deterministic, behaviourally plausible source events and exposes known mechanisms for method checks. It contains no real customer data.
2. **Warehouse and SQL models** transform events into analysis-ready customer, cohort, funnel, experiment, and feature tables.
3. **Decision utilities** provide reusable statistical power, causal diagnostics, and unit-economics calculations. They deliberately separate assumptions from presentation.
4. **Analyses and reporting** consume versioned outputs to produce notebooks, a PDF report, and the project site. They do not reimplement business definitions.

## Contracts and reproducibility

Dates are UTC calendar dates. Customer IDs are synthetic opaque identifiers. A run records its seed, mode, source snapshot, and configuration. Development and full modes use the same definitions and code path. Generated full datasets are not source-controlled.

Every decision-facing result should carry its cohort/window, denominator, confidence interval where applicable, and limitation. Association, prediction, and causal estimates remain separate outputs: none is silently substituted for another.

## Boundaries

The warehouse owns canonical metric tables; the `pulse` utilities own calculations over supplied tabular inputs; reports own narrative. This prevents notebooks, SQL, and dashboards from drifting into competing definitions.
