CREATE OR REPLACE VIEW stg_transactions AS
SELECT transaction_id, customer_id, CAST(timestamp AS TIMESTAMP) AS transaction_at,
       transaction_type, merchant_category, amount, status, channel
FROM transactions
WHERE status = 'settled' AND amount >= 0;
