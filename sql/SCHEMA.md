# Warehouse schema

| Table | Grain | Key | Use |
|---|---|---|---|
| customers | one row per customer | customer_id | signup and acquisition dimensions |
| customer_events | one event | event_id | journey milestones |
| transactions | one attempted transaction (settled or failed) | transaction_id | transaction quality, financial activity and value |
| product_holdings | one product opening | holding_id | breadth and adoption |
| marketing_exposures | one exposure | exposure_id | contact history |
| experiment_assignments | one customer-experiment assignment | experiment_id, customer_id | randomization |
| experiment_outcomes | one customer-experiment outcome | experiment_id, customer_id | primary and downstream metrics |
