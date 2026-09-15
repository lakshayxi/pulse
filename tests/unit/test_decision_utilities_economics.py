import pandas as pd

from pulse.economics import expected_incremental_value, target_customers


def test_economics_only_targets_positive_value_customers():
    data = pd.DataFrame(
        {
            "customer_id": ["a", "b"],
            "churn": [0.8, 0.1],
            "response": [0.5, 0.1],
            "value": [100.0, 20.0],
        }
    )
    selected = target_customers(
        data,
        churn_col="churn",
        response_col="response",
        value_col="value",
        treatment_effect_if_response=0.5,
        contact_cost=5.0,
    )
    assert selected["customer_id"].tolist() == ["a"]
    assert (
        expected_incremental_value(
            data["churn"],
            data["response"],
            data["value"],
            treatment_effect_if_response=0.5,
            contact_cost=5.0,
        ).iloc[0]
        == 15.0
    )
