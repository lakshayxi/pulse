# Methodology and causal limits

Pulse uses deterministic synthetic data to demonstrate analytical method, not production performance. Known simulation mechanisms can validate selected calculations, but they do not remove the need for real-world validation.

Public disclosures from SBI, Axis Bank, HDFC Bank, ICICI Bank, and Kotak Mahindra Bank inform the lifecycle generator's structure. Those sources motivate distinct registered and active states, heterogeneous product depth, delayed activation, reactivation, and cohort-level acquisition or operational shocks. They do not publish comparable D7/D30/D60/D90 signup-cohort matrices, so Pulse does not numerically calibrate its retention rates to them. See [external calibration](external_calibration.md) for the evidence and boundary.

For the randomized intervention, assignment precedes outcomes and the primary estimate is intent-to-treat. Balance checks and assignment/outcome integrity are still required.

For a selected-region intervention where randomization was unavailable, Pulse estimates a difference-in-differences (DiD) effect and a stabilized inverse-probability-of-treatment weighted (IPTW) estimate. DiD requires parallel untreated trends, no differential contemporaneous shocks, stable composition, and credible timing. The report should show pre-period trends and avoid causal claims where these are not credible.

Stabilized IPTW estimates treatment probabilities from pre-treatment covariates, then weights observations by marginal treatment prevalence divided by the observed treatment probability. It requires exchangeability conditional on measured covariates, positivity/overlap, correct propensity specification, and no post-treatment features. Diagnostics include propensity ranges, extreme weights, effective sample size, and weighted standardized mean differences. Positivity failures, severe extreme weights, or persistent imbalance are reasons to trim/re-specify or not trust the estimate.

Pulse evaluates churn and response models with temporal splits, calibration, concentration or precision at operating capacity, and stability by cohort and segment. Scores feed an economic policy only after considering uplift or response assumptions, customer value, contact cost, and possible customer harm.
