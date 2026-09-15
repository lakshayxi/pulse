CREATE OR REPLACE TABLE customer_daily_metrics AS
WITH days AS (
 SELECT c.customer_id, day.activity_date::DATE AS activity_date
 FROM stg_customers c,
 LATERAL generate_series(c.signup_date, c.signup_date + INTERVAL 119 DAY, INTERVAL 1 DAY) AS day(activity_date)
), daily AS (
 SELECT d.customer_id, d.activity_date, COUNT(t.transaction_id) AS transaction_count,
        COALESCE(SUM(t.amount), 0) AS transaction_amount
 FROM days d LEFT JOIN stg_transactions t ON t.customer_id = d.customer_id AND t.transaction_at::DATE = d.activity_date
   AND t.transaction_type IN ('card_transaction', 'transfer', 'bill_payment')
 GROUP BY ALL
)
SELECT *, transaction_count > 0 AS active FROM daily;
