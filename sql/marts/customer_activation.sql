CREATE OR REPLACE TABLE customer_activation AS
WITH funding AS (
  SELECT customer_id,
    MIN(event_timestamp::DATE) FILTER (WHERE event_type = 'account_funded') AS funded_date
  FROM customer_events
  GROUP BY customer_id
), meaningful_transactions AS (
  SELECT t.customer_id, t.transaction_id, t.transaction_at::DATE AS transaction_date,
    c.signup_date, c.account_funded,
    transaction_at::DATE - c.signup_date AS day_from_signup
  FROM stg_transactions t
  JOIN stg_customers c USING (customer_id)
  WHERE t.status = 'settled'
    AND t.transaction_type IN ('card_transaction', 'transfer', 'bill_payment')
), transaction_summary AS (
  SELECT customer_id,
    MIN(transaction_date) FILTER (WHERE day_from_signup BETWEEN 0 AND 7) AS first_transaction_date,
    COUNT(DISTINCT transaction_id) AS settled_meaningful_transaction_count,
    COUNT(*) FILTER (WHERE day_from_signup BETWEEN 30 AND 36) > 0 AS d30_active
  FROM meaningful_transactions
  GROUP BY customer_id
)
SELECT c.customer_id, c.signup_date, c.acquisition_channel,
  f.funded_date,
  ts.first_transaction_date,
  COALESCE(ts.settled_meaningful_transaction_count, 0) AS settled_meaningful_transaction_count,
  COALESCE(ts.d30_active, FALSE) AS d30_active,
  (c.account_funded AND ts.first_transaction_date IS NOT NULL) AS activated
FROM stg_customers c
LEFT JOIN funding f USING (customer_id)
LEFT JOIN transaction_summary ts USING (customer_id);
