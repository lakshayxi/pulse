"""Small, deterministic matplotlib visualizations saved in portable formats."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

PALETTE = {
    "ink": "#132238",
    "blue": "#3973ac",
    "teal": "#2c8c88",
    "orange": "#d48a3c",
    "muted": "#728096",
}


def _save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    fig.savefig(path.with_suffix(".png"), dpi=180, bbox_inches="tight")
    plt.close(fig)


def funnel(frame: pd.DataFrame, output: str | Path) -> None:
    frame = frame.loc[frame["metric_scope"].eq("sequential_funnel")].copy()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.barh(frame["stage"], frame["customers"], color=PALETTE["blue"])
    ax.invert_yaxis()
    ax.set_xlabel("Customers")
    ax.set_title("Customer journey funnel")
    total = float(frame.iloc[0]["customers"])
    for bar, customers in zip(bars, frame["customers"], strict=True):
        ax.text(
            bar.get_width() + total * 0.012,
            bar.get_y() + bar.get_height() / 2,
            f"{int(customers):,}  ({customers / total:.0%})",
            va="center",
            fontsize=8,
            color=PALETTE["ink"],
        )
    ax.set_xlim(0, total * 1.18)
    _save(fig, Path(output))


def cohort_retention(frame: pd.DataFrame, output: str | Path) -> None:
    pivot = frame.pivot(index="cohort_month", columns="horizon_days", values="retention")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    values = pivot.to_numpy(dtype=float)
    lower = max(0.0, float(pd.Series(values.ravel()).quantile(0.02)) - 0.02)
    upper = min(1.0, float(pd.Series(values.ravel()).quantile(0.98)) + 0.02)
    image = ax.imshow(values, aspect="auto", cmap="Blues", vmin=lower, vmax=upper)
    ax.set_xticks(range(len(pivot.columns)), [f"D{v}" for v in pivot.columns])
    ax.set_yticks(range(len(pivot.index)), pivot.index)
    midpoint = (lower + upper) / 2
    for row in range(values.shape[0]):
        for col in range(values.shape[1]):
            value = values[row, col]
            if pd.notna(value):
                ax.text(
                    col,
                    row,
                    f"{value:.0%}",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white" if value > midpoint else PALETTE["ink"],
                )
    fig.colorbar(image, ax=ax, label="Retention")
    ax.set_title("Signup cohort retention")
    _save(fig, Path(output))


def calibration(frame: pd.DataFrame, output: str | Path) -> None:
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    limit = max(0.15, float(frame[["predicted_rate", "observed_rate"]].max().max()) * 1.25)
    ax.plot([0, limit], [0, limit], "--", color=PALETTE["muted"], label="perfect calibration")
    ax.plot(
        frame["predicted_rate"], frame["observed_rate"], "o-", color=PALETTE["teal"], label="model"
    )
    ax.set(xlabel="Mean predicted risk", ylabel="Observed churn rate", title="Churn calibration")
    ax.set_xlim(0, limit)
    ax.set_ylim(0, limit)
    ax.legend()
    _save(fig, Path(output))


def lift(frame: pd.DataFrame, output: str | Path) -> None:
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    ax.plot(frame["target_fraction"] * 100, frame["lift"], "o-", color=PALETTE["orange"])
    ax.axhline(1, linestyle="--", color=PALETTE["muted"])
    ax.set(xlabel="Targeted population (%)", ylabel="Lift", title="Churn risk lift")
    _save(fig, Path(output))


def effect_ci(stats: dict[str, float], output: str | Path) -> None:
    fig, ax = plt.subplots(figsize=(5.5, 2.8))
    effect = stats["risk_difference"] * 100
    low, high = stats["ci_low"] * 100, stats["ci_high"] * 100
    ax.errorbar(effect, 0, xerr=[[effect - low], [high - effect]], fmt="o", color=PALETTE["teal"])
    ax.axvline(0, linestyle="--", color=PALETTE["muted"])
    ax.set(
        yticks=[],
        xlabel="Activation risk difference (percentage points)",
        title="RCT effect with 95% CI",
    )
    ax.text(
        effect,
        0.12,
        f"{effect:.2f} pp  (95% CI {low:.2f} to {high:.2f})",
        ha="center",
        fontsize=9,
        color=PALETTE["ink"],
    )
    _save(fig, Path(output))


def did_trends(frame: pd.DataFrame, output: str | Path) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    for treatment, label, color in [
        (0, "comparison region", PALETTE["muted"]),
        (1, "selected region", PALETTE["orange"]),
    ]:
        subset = frame.loc[frame["treatment"].eq(treatment)]
        ax.plot(subset["relative_week"], subset["active_rate"], "o-", label=label, color=color)
    ax.axvline(-0.5, linestyle="--", color=PALETTE["ink"])
    ax.set(
        xlabel="Week relative to campaign",
        ylabel="Weekly active rate",
        title="Selected-region campaign trends",
    )
    ax.legend()
    _save(fig, Path(output))


def strategy_value(frame: pd.DataFrame, output: str | Path) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.bar(frame["strategy"], frame["expected_net_value"], color=PALETTE["blue"])
    ax.axhline(0, linestyle="--", color=PALETTE["muted"])
    ax.tick_params(axis="x", rotation=30)
    ax.set(ylabel="Expected net value", title="Targeting strategy comparison")
    _save(fig, Path(output))


def drift(frame: pd.DataFrame, output: str | Path) -> None:
    subset = frame.loc[frame["kind"].eq("feature_drift")]
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.bar(subset["measure"], subset["value"], color=PALETTE["teal"])
    ax.axhline(0.1, linestyle="--", color=PALETTE["orange"], label="low/moderate threshold")
    ax.tick_params(axis="x", rotation=30)
    ax.set(ylabel="Population stability index", title="Temporal feature drift")
    ax.legend()
    _save(fig, Path(output))


def model_performance_over_time(frame: pd.DataFrame, output: str | Path) -> None:
    """Plot holdout discrimination, base rate, and targeting lift by bucket."""
    fig, axes = plt.subplots(2, 1, figsize=(7, 5.5), sharex=True)
    x = pd.to_datetime(frame["time_bucket"])
    axes[0].plot(x, frame["roc_auc"], "o-", color=PALETTE["blue"], label="ROC AUC")
    axes[0].plot(x, frame["pr_auc"], "o-", color=PALETTE["teal"], label="PR AUC")
    axes[0].plot(x, frame["base_rate"], "o--", color=PALETTE["muted"], label="base rate")
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("Rate / AUC")
    axes[0].legend(ncol=3, fontsize=8)
    axes[1].plot(x, frame["lift_at_10pct"], "o-", color=PALETTE["orange"], label="lift @ 10%")
    axes[1].axhline(1, linestyle=":", color=PALETTE["muted"])
    axes[1].set_ylabel("Lift @ 10%")
    calibration_axis = axes[1].twinx()
    calibration_axis.plot(
        x,
        frame["calibration_error"],
        "o--",
        color=PALETTE["ink"],
        label="calibration error",
    )
    calibration_axis.set_ylabel("Absolute calibration error")
    axes[1].set_xlabel("Holdout month")
    axes[1].set_xticks(x, [value.strftime("%b\n%Y") for value in x])
    handles, labels = axes[1].get_legend_handles_labels()
    handles_2, labels_2 = calibration_axis.get_legend_handles_labels()
    axes[1].legend(handles + handles_2, labels + labels_2, fontsize=8, loc="upper left")
    fig.suptitle("Temporal holdout model monitoring")
    _save(fig, Path(output))


def model_comparison(frame: pd.DataFrame, output: str | Path) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.bar(frame["model"], frame["roc_auc"], color=PALETTE["blue"])
    ax.tick_params(axis="x", rotation=25)
    ax.set(ylim=(0, 1), ylabel="ROC AUC", title="Temporal churn model comparison")
    _save(fig, Path(output))
