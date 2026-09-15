CREATE OR REPLACE TABLE retention_cohorts AS
WITH horizon AS (
 SELECT c.* FROM stg_customers c
 WHERE c.signup_date + INTERVAL 96 DAY <= (SELECT MAX(activity_date) FROM customer_daily_metrics)
)
SELECT c.signup_date AS cohort_date, COUNT(*) AS cohort_size,
  AVG(CASE WHEN EXISTS (SELECT 1 FROM customer_daily_metrics d WHERE d.customer_id=c.customer_id AND d.activity_date BETWEEN c.signup_date+INTERVAL 7 DAY AND c.signup_date+INTERVAL 13 DAY AND d.active) THEN 1 ELSE 0 END) AS d7_retention,
  AVG(CASE WHEN EXISTS (SELECT 1 FROM customer_daily_metrics d WHERE d.customer_id=c.customer_id AND d.activity_date BETWEEN c.signup_date+INTERVAL 30 DAY AND c.signup_date+INTERVAL 36 DAY AND d.active) THEN 1 ELSE 0 END) AS d30_retention,
  AVG(CASE WHEN EXISTS (SELECT 1 FROM customer_daily_metrics d WHERE d.customer_id=c.customer_id AND d.activity_date BETWEEN c.signup_date+INTERVAL 60 DAY AND c.signup_date+INTERVAL 66 DAY AND d.active) THEN 1 ELSE 0 END) AS d60_retention,
  AVG(CASE WHEN EXISTS (SELECT 1 FROM customer_daily_metrics d WHERE d.customer_id=c.customer_id AND d.activity_date BETWEEN c.signup_date+INTERVAL 90 DAY AND c.signup_date+INTERVAL 96 DAY AND d.active) THEN 1 ELSE 0 END) AS d90_retention
FROM horizon c GROUP BY 1 ORDER BY 1;
