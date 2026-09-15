WITH base AS (
  SELECT c.*, a.activated, a.d30_active, a.settled_meaningful_transaction_count
  FROM stg_customers c JOIN customer_activation a USING (customer_id)
), steps AS (
  SELECT 1 AS stage_order, 'signup' AS stage, COUNT(*) AS customers, 'sequential_funnel' AS metric_scope FROM base
  UNION ALL SELECT 2, 'onboarding_completed', SUM(onboarding_completed::INT), 'sequential_funnel' FROM base
  UNION ALL SELECT 3, 'account_funded', SUM(account_funded::INT), 'sequential_funnel' FROM base
  UNION ALL SELECT 4, 'first_transaction_7d', SUM(activated::INT), 'sequential_funnel' FROM base
  UNION ALL SELECT 5, 'repeat_usage', SUM((activated AND settled_meaningful_transaction_count >= 2)::INT), 'sequential_funnel' FROM base
  UNION ALL SELECT 6, 'sustained_engagement_d30', SUM((activated AND d30_active)::INT), 'sequential_funnel' FROM base
  UNION ALL SELECT 7, 'd30_retention_overall', SUM(d30_active::INT), 'overall_retention' FROM base
)
SELECT stage, customers, metric_scope,
       customers::DOUBLE / NULLIF(FIRST_VALUE(customers) OVER (ORDER BY stage_order), 0) AS conversion_from_signup,
       CASE WHEN metric_scope = 'sequential_funnel' THEN customers::DOUBLE / NULLIF(LAG(customers) OVER (ORDER BY stage_order), 0) END AS conversion_from_previous
FROM steps ORDER BY stage_order;
