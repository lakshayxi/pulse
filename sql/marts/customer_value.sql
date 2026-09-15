CREATE OR REPLACE TABLE customer_value AS
SELECT c.customer_id, COUNT(t.transaction_id) AS transaction_count,
       SUM(t.amount) AS gross_volume,
       COUNT(DISTINCT t.merchant_category) AS category_breadth,
       SUM(t.amount) * 0.0025 - COUNT(t.transaction_id) * 0.08 - 1.50 AS contribution_proxy
FROM stg_customers c LEFT JOIN stg_transactions t USING (customer_id)
GROUP BY c.customer_id;
