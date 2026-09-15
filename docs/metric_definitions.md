# Metric definitions

The canonical denominator is always stated alongside a result. A **meaningful transaction** is a settled, non-negative transaction whose `transaction_type` is `card_transaction`, `transfer`, or `bill_payment`. The observed schema has no `is_meaningful` flag; this type/status rule is the canonical definition.

| Metric | Definition |
|---|---|
| Signup | Customer created an account (`signup_date`). |
| Onboarding completion | Customer has a successful required onboarding/identity completion event. |
| Funded | Customer has at least one successful funding event. |
| Activation | Customer is funded and completes at least one meaningful transaction in days 0-7 inclusive after signup. |
| D7 retention | Customer has a meaningful transaction on days 7-13 after signup. |
| D30 retention | Customer has a meaningful transaction on days 30-36 after signup. |
| D60 retention | Customer has a meaningful transaction on days 60-66 after signup. |
| D90 retention | Customer has a meaningful transaction on days 90-96 after signup. |
| Churn | Customer was active (at least one meaningful transaction) in the preceding 30 days and has no meaningful activity in the following 30 days. The scoring as-of date separates the two windows. |
| RCT primary outcome | D7 activation: at least one meaningful transaction in signup days 0-7, measured for customers funded by day 3 and not activated at eligibility. |
| RCT eligibility | Funded by signup day 3 and no meaningful transaction before assignment. |

Funnels use the immediately preceding stage as denominator unless labelled as a signup-conversion rate. Cohort retention requires sufficiently mature cohorts: a cohort is excluded when its observation cutoff cannot cover the entire stated window.
