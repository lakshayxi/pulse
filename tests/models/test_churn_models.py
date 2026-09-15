from pulse.features.temporal import build_churn_snapshots
from pulse.models.churn import temporal_split, train_churn_models
from pulse.simulation.generator import generate_dataset


def test_churn_train_predict_and_temporal_split() -> None:
    tables = generate_dataset(1_000, seed=1729)
    snapshots = build_churn_snapshots(
        tables["customers"],
        tables["transactions"],
        tables["product_holdings"],
        tables["customer_events"],
    )
    split = temporal_split(snapshots)
    assert split.train.feature_cutoff.max() <= split.test.feature_cutoff.min()
    result = train_churn_models(snapshots)
    probabilities = result["probabilities"]["regularized_logistic"]
    assert probabilities.between(0, 1).all()
    assert {"rule_baseline", "regularized_logistic", "hist_gradient_boosting"} == set(
        result["comparison"]["model"]
    )
