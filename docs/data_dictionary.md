# Pulse data dictionary

All records are deterministic synthetic data for a fictional mobile-first consumer bank. Dates are stored as date-like values or naive simulation timestamps; they are not asserted to be UTC.

| Table | Exact columns | Grain |
|---|---|---|
| `customers` | `customer_id`, `signup_date`, `acquisition_channel`, `age_band`, `region_group`, `initial_segment`, `onboarding_completed`, `account_funded` | one row per customer |
| `customer_events` | `event_id`, `customer_id`, `event_timestamp`, `event_type` | one observed event |
| `transactions` | `transaction_id`, `customer_id`, `timestamp`, `transaction_type`, `merchant_category`, `amount`, `status`, `channel` | one attempted transaction; `status` is `settled` or `failed` |
| `product_holdings` | `holding_id`, `customer_id`, `product_type`, `opened_at` | one product opening |
| `marketing_exposures` | `exposure_id`, `customer_id`, `campaign_id`, `exposure_timestamp`, `arm` | one delivered experimental or campaign exposure |
| `experiment_assignments` | `experiment_id`, `customer_id`, `assignment_date`, `arm`, `eligible` | one customer-experiment assignment; eligible assignments occur on signup day 2 |
| `experiment_outcomes` | `experiment_id`, `customer_id`, `first_week_activation`, `d30_active`, `d30_sustained_engagement`, `support_contacts`, `failed_payment_rate`, `incentive_cost` | one customer-experiment outcome row |
| `campaign_assignments` | `campaign_id`, `customer_id`, `campaign_date`, `eligible`, `selected_region`, `region_group`, `treatment_probability` | one customer selected-region campaign assignment; treatment is probabilistic and region-influenced |

`first_week_activation` is funded plus at least one settled transaction whose type is `card_transaction`, `transfer`, or `bill_payment` in signup calendar days 0-7 inclusive. `d30_active` is overall activity in days 30-36; `d30_sustained_engagement` additionally requires activation. `failed_payment_rate` is failed first-week attempts divided by all first-week attempts, with zero when no attempt occurred. `incentive_cost` is fictional currency units per customer.

Warehouse-only derived relations include `stg_customers`, `stg_transactions`, `customer_activation`, `customer_daily_metrics`, `customer_value`, `experiment_analysis_base`, `modelling_features`, and `retention_cohorts`; their definitions and keys are in [sql/SCHEMA.md](../sql/SCHEMA.md).
