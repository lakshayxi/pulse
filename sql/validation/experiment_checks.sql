SELECT 'eligible_has_assignment' AS check_name,
       COUNT(*) FILTER (WHERE eligible AND arm IS NULL) = 0 AS passed
FROM experiment_assignments
UNION ALL
SELECT 'no_duplicate_assignments', COUNT(*) = COUNT(DISTINCT customer_id) FROM experiment_assignments
UNION ALL
SELECT 'campaign_assignment_customer_exists', COUNT(*) = 0
FROM campaign_assignments a LEFT JOIN customers c USING (customer_id) WHERE c.customer_id IS NULL
UNION ALL
SELECT 'eligible_rct_has_no_pre_assignment_transaction', COUNT(*) = 0
FROM experiment_assignments a
JOIN transactions t USING (customer_id)
WHERE a.eligible AND t.timestamp < a.assignment_date
UNION ALL
SELECT 'outcome_activation_matches_calendar_day_contract', COUNT(*) = 0
FROM (
  SELECT o.customer_id
  FROM experiment_outcomes o
  JOIN customers c USING (customer_id)
  LEFT JOIN transactions t ON t.customer_id = o.customer_id
    AND t.status = 'settled'
    AND t.transaction_type IN ('card_transaction', 'transfer', 'bill_payment')
    AND CAST(t.timestamp AS DATE) BETWEEN c.signup_date AND c.signup_date + INTERVAL 7 DAY
  GROUP BY o.customer_id, o.first_week_activation, c.account_funded
  HAVING o.first_week_activation <> (c.account_funded AND COUNT(t.transaction_id) > 0)
) mismatches;
