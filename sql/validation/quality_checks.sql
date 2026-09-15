SELECT 'customer_key_unique' AS check_name, COUNT(*) = COUNT(DISTINCT customer_id) AS passed FROM customers
UNION ALL SELECT 'transaction_key_unique', COUNT(*) = COUNT(DISTINCT transaction_id) FROM transactions
UNION ALL SELECT 'nonnegative_amounts', COALESCE(MIN(amount) >= 0, TRUE) FROM transactions
UNION ALL SELECT 'valid_event_time', COALESCE(MIN(event_timestamp) >= (SELECT MIN(signup_date) FROM customers), TRUE) FROM customer_events
UNION ALL SELECT 'events_after_signup', COUNT(*) = 0
  FROM customer_events e JOIN customers c USING (customer_id) WHERE e.event_timestamp < c.signup_date
UNION ALL SELECT 'settled_amount_nonnegative', COUNT(*) = 0
  FROM transactions WHERE status = 'settled' AND amount < 0
UNION ALL SELECT 'transaction_customer_exists', COUNT(*) = 0
  FROM transactions t LEFT JOIN customers c USING (customer_id) WHERE c.customer_id IS NULL
UNION ALL SELECT 'event_customer_exists', COUNT(*) = 0
  FROM customer_events e LEFT JOIN customers c USING (customer_id) WHERE c.customer_id IS NULL;
