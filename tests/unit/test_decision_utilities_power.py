from pulse.experimentation.power import (
    minimum_detectable_effect,
    required_sample_size_per_arm,
    two_proportion_z_test,
)


def test_sample_size_and_mde_move_in_expected_directions():
    small_effect = required_sample_size_per_arm(0.2, 0.02)
    large_effect = required_sample_size_per_arm(0.2, 0.05)
    assert small_effect > large_effect
    assert minimum_detectable_effect(0.2, 10_000) < minimum_detectable_effect(0.2, 1_000)


def test_two_proportion_test_reports_positive_lift():
    result = two_proportion_z_test(130, 1_000, 100, 1_000)
    assert result["risk_difference"] == 0.03
    assert result["ci_low"] < 0.03 < result["ci_high"]
    assert result["p_value"] < 0.05
