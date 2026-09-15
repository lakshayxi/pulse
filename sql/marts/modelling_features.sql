CREATE OR REPLACE TABLE modelling_features AS
SELECT c.customer_id, c.signup_date, c.acquisition_channel, c.initial_segment,
       ca.activated, COALESCE(v.transaction_count, 0) AS transaction_count,
       COALESCE(v.category_breadth, 0) AS category_breadth,
       COALESCE(v.contribution_proxy, 0) AS contribution_proxy
FROM stg_customers c JOIN customer_activation ca USING (customer_id)
LEFT JOIN customer_value v USING (customer_id);
