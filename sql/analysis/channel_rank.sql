SELECT acquisition_channel, COUNT(*) AS signups,
       AVG(activated::INT) AS activation_rate,
       RANK() OVER (ORDER BY AVG(contribution_proxy) DESC) AS value_rank,
       AVG(contribution_proxy) AS avg_contribution
FROM modelling_features GROUP BY acquisition_channel;
