SELECT arm, COUNT(*) AS customers, AVG(first_week_activation::INT) AS activation_rate,
       AVG(d30_active::INT) AS d30_rate
FROM experiment_analysis_base GROUP BY arm ORDER BY arm;
