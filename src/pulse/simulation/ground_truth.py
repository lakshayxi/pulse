"""Private simulation mechanisms. Analytical code must not import this module."""

CHANNEL_QUALITY = {"organic": 0.62, "referral": 0.78, "paid": 0.48, "partner": 0.55}
SEGMENT_ENGAGEMENT = {"everyday": 0.72, "builder": 0.58, "starter": 0.38}
TREATMENT_LIFT = 0.09

# These mechanisms are deliberately kept out of the observed customer and
# transaction tables. They provide a stable synthetic lifecycle rather than
# turning retention into an artifact of uniform random transaction timing.
ENGAGEMENT_SCALE_BASE_DAYS = 54.0
ENGAGEMENT_SCALE_QUALITY_DAYS = 76.0
COHORT_SEASONALITY_AMPLITUDE = 0.08
POST_ACTIVATION_DAILY_RATE = 0.12

# These are intentionally broad mechanisms, not estimates of any one bank.
# They create the delayed adoption, product-depth, and campaign-period
# heterogeneity visible in real digital-bank operating disclosures.
LATE_ACTIVATION_BASE_RATE = 0.22
LATE_ACTIVATION_QUALITY_RATE = 0.12
LATE_ENGAGEMENT_SCALE_DAYS = 42.0
PRODUCT_DEPTH_NOISE_SD = 0.16
REACTIVATION_BASE_RATE = 0.14

# Fixed operational/acquisition-period shocks prevent monthly cohorts from
# becoming smooth copies of one another. The values are synthetic and are
# documented as directional calibration only.
COHORT_OPERATIONAL_SHOCKS = (0.84, 1.06, 1.22, 0.91, 1.15, 0.78, 1.18, 0.95, 1.08)
# The June-period pulse represents a synthetic product/campaign re-engagement
# wave. It is intentionally cohort-specific so a mature cohort can show a
# local D60 bump without making the aggregate curve non-monotonic.
COHORT_REACTIVATION_SHOCKS = (1.35, 0.62, 1.18, 1.52, 0.58, 3.60, 0.76, 1.44, 0.90)
