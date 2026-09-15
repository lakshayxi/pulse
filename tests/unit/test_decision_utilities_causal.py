import pandas as pd

from pulse.causal import (
    balance_table,
    difference_in_differences,
    effective_sample_size,
    stabilized_iptw_weights,
)


def test_did_recovers_difference_of_changes():
    data = pd.DataFrame(
        {"region_treated": [1, 1, 0, 0], "post": [0, 1, 0, 1], "outcome": [10.0, 15.0, 8.0, 10.0]}
    )
    assert (
        difference_in_differences(
            data, group_col="region_treated", post_col="post", outcome_col="outcome"
        )["did_effect"]
        == 3.0
    )


def test_stabilized_weights_and_balance_diagnostics():
    data = pd.DataFrame(
        {
            "treatment": [1, 1, 0, 0],
            "propensity": [0.8, 0.7, 0.2, 0.3],
            "tenure": [10.0, 11.0, 9.0, 8.0],
        }
    )
    data["weight"] = stabilized_iptw_weights(data["treatment"], data["propensity"])
    assert effective_sample_size(data["weight"]) <= len(data)
    report = balance_table(
        data, treatment_col="treatment", covariates=["tenure"], weight_col="weight"
    )
    assert list(report["covariate"]) == ["tenure"]
