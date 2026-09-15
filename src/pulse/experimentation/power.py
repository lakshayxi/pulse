"""Transparent normal-approximation helpers for binary experiments."""

from __future__ import annotations

from math import erf, sqrt


def _normal_cdf(value: float) -> float:
    return (1.0 + erf(value / sqrt(2.0))) / 2.0


def _normal_ppf(probability: float) -> float:
    """Acklam approximation to the inverse standard-normal CDF."""
    if not 0.0 < probability < 1.0:
        raise ValueError("probability must be strictly between 0 and 1")
    a = (
        -39.69683028665376,
        220.9460984245205,
        -275.9285104469687,
        138.357751867269,
        -30.66479806614716,
        2.506628277459239,
    )
    b = (
        -54.47609879822406,
        161.5858368580409,
        -155.6989798598866,
        66.80131188771972,
        -13.28068155288572,
    )
    c = (
        -0.007784894002430293,
        -0.3223964580411365,
        -2.400758277161838,
        -2.549732539343734,
        4.374664141464968,
        2.938163982698783,
    )
    d = (0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416)
    low, high = 0.02425, 0.97575
    if probability < low:
        q = sqrt(-2.0 * __import__("math").log(probability))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if probability > high:
        return -_normal_ppf(1.0 - probability)
    q = probability - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    )


def required_sample_size_per_arm(
    baseline_rate: float, absolute_effect: float, *, alpha: float = 0.05, power: float = 0.8
) -> int:
    """Approximate equal-arm sample size for a two-sided two-proportion test."""
    treatment_rate = baseline_rate + absolute_effect
    if not 0 < baseline_rate < 1 or not 0 < treatment_rate < 1:
        raise ValueError("baseline_rate and baseline_rate + absolute_effect must be in (0, 1)")
    if not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError("alpha and power must be in (0, 1)")
    z_alpha, z_power = _normal_ppf(1 - alpha / 2), _normal_ppf(power)
    pooled = (baseline_rate + treatment_rate) / 2
    numerator = (
        z_alpha * sqrt(2 * pooled * (1 - pooled))
        + z_power
        * sqrt(baseline_rate * (1 - baseline_rate) + treatment_rate * (1 - treatment_rate))
    ) ** 2
    return int(__import__("math").ceil(numerator / absolute_effect**2))


def minimum_detectable_effect(
    baseline_rate: float, sample_size_per_arm: int, *, alpha: float = 0.05, power: float = 0.8
) -> float:
    """Return a conservative local normal-approximation absolute MDE."""
    if not 0 < baseline_rate < 1 or sample_size_per_arm <= 0:
        raise ValueError("baseline_rate must be in (0, 1) and sample_size_per_arm positive")
    return (_normal_ppf(1 - alpha / 2) + _normal_ppf(power)) * sqrt(
        2 * baseline_rate * (1 - baseline_rate) / sample_size_per_arm
    )


def two_proportion_z_test(
    treatment_successes: int,
    treatment_total: int,
    control_successes: int,
    control_total: int,
    *,
    alpha: float = 0.05,
) -> dict[str, float]:
    """Return risk difference, Wald CI, and pooled two-sided z-test p-value."""
    if min(treatment_successes, control_successes) < 0 or min(treatment_total, control_total) <= 0:
        raise ValueError("counts must be non-negative and totals positive")
    if treatment_successes > treatment_total or control_successes > control_total:
        raise ValueError("successes cannot exceed totals")
    pt, pc = treatment_successes / treatment_total, control_successes / control_total
    effect = pt - pc
    se = sqrt(pt * (1 - pt) / treatment_total + pc * (1 - pc) / control_total)
    z_crit = _normal_ppf(1 - alpha / 2)
    pooled = (treatment_successes + control_successes) / (treatment_total + control_total)
    pooled_se = sqrt(pooled * (1 - pooled) * (1 / treatment_total + 1 / control_total))
    z_stat = effect / pooled_se if pooled_se else 0.0
    return {
        "treatment_rate": pt,
        "control_rate": pc,
        "risk_difference": effect,
        "ci_low": effect - z_crit * se,
        "ci_high": effect + z_crit * se,
        "z_statistic": z_stat,
        "p_value": 2 * (1 - _normal_cdf(abs(z_stat))),
    }
