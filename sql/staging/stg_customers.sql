-- One row per customer; source columns are typed and renamed at the warehouse boundary.
CREATE OR REPLACE VIEW stg_customers AS
SELECT customer_id, CAST(signup_date AS DATE) AS signup_date, acquisition_channel,
       age_band, region_group, initial_segment, onboarding_completed, account_funded
FROM customers;
