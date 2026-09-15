CREATE OR REPLACE TABLE experiment_analysis_base AS
SELECT a.experiment_id, a.customer_id, a.arm, a.eligible,
       o.first_week_activation, o.d30_active,
       ROW_NUMBER() OVER (PARTITION BY a.customer_id ORDER BY a.assignment_date) AS assignment_version
FROM experiment_assignments a LEFT JOIN experiment_outcomes o USING (experiment_id, customer_id)
WHERE a.eligible;
