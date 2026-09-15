"""Temporal churn and response propensity models with compact, auditable contracts."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from pulse.features.temporal import FEATURE_COLUMNS, validate_snapshot_leakage

from .evaluation import model_metrics


@dataclass
class TemporalSplit:
    train: pd.DataFrame
    test: pd.DataFrame


def temporal_split(
    frame: pd.DataFrame, *, cutoff_col: str = "feature_cutoff", test_fraction: float = 0.25
) -> TemporalSplit:
    if not 0 < test_fraction < 1 or frame.empty:
        raise ValueError("frame must be non-empty and test_fraction must be in (0, 1)")
    ordered = frame.sort_values(cutoff_col).copy()
    boundary = ordered[cutoff_col].iloc[max(1, int(len(ordered) * (1 - test_fraction))) - 1]
    train, test = ordered[ordered[cutoff_col] <= boundary], ordered[ordered[cutoff_col] > boundary]
    if (
        test.empty
    ):  # identical dates: preserve time contract and make an explicit deterministic fallback
        boundary = ordered[cutoff_col].quantile(1 - test_fraction)
        train, test = (
            ordered.iloc[: int(len(ordered) * (1 - test_fraction))],
            ordered.iloc[int(len(ordered) * (1 - test_fraction)) :],
        )
    return TemporalSplit(train.reset_index(drop=True), test.reset_index(drop=True))


def _feature_columns(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    numeric = [c for c in FEATURE_COLUMNS if c in frame]
    categorical = [c for c in ["acquisition_channel", "initial_segment"] if c in frame]
    return numeric, categorical


def _preprocessor(numeric: list[str], categorical: list[str], *, scale: bool) -> ColumnTransformer:
    numeric_pipe = Pipeline(
        [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
        if scale
        else [("impute", SimpleImputer(strategy="median"))]
    )
    return ColumnTransformer(
        [
            ("numeric", numeric_pipe, numeric),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
        ]
    )


def train_churn_models(snapshots: pd.DataFrame) -> dict[str, object]:
    split = temporal_split(snapshots)
    numeric, categorical = _feature_columns(snapshots)
    features = numeric + categorical
    validate_snapshot_leakage(snapshots[features + ["feature_cutoff"]])
    X_train, y_train = split.train[features], split.train["churned"]
    X_test, y_test = split.test[features], split.test["churned"]
    baseline_probability = pd.Series(float(y_train.mean()), index=X_test.index)
    logistic = Pipeline(
        [
            ("prep", _preprocessor(numeric, categorical, scale=True)),
            ("model", LogisticRegression(C=0.5, max_iter=500, random_state=1729)),
        ]
    )
    tree = Pipeline(
        [
            ("prep", _preprocessor(numeric, categorical, scale=False)),
            (
                "model",
                HistGradientBoostingClassifier(
                    max_iter=150,
                    learning_rate=0.06,
                    max_leaf_nodes=15,
                    l2_regularization=1.0,
                    random_state=1729,
                ),
            ),
        ]
    )
    logistic.fit(X_train, y_train)
    tree.fit(X_train, y_train)
    probabilities = {
        "rule_baseline": baseline_probability,
        "regularized_logistic": pd.Series(logistic.predict_proba(X_test)[:, 1], index=X_test.index),
        "hist_gradient_boosting": pd.Series(tree.predict_proba(X_test)[:, 1], index=X_test.index),
    }
    comparison = pd.DataFrame(
        [{"model": name, **model_metrics(y_test, scores)} for name, scores in probabilities.items()]
    )
    return {
        "split": split,
        "features": features,
        "logistic": logistic,
        "tree": tree,
        "probabilities": probabilities,
        "comparison": comparison,
        "test_target": y_test,
    }


def train_response_propensity(
    assignments: pd.DataFrame, outcomes: pd.DataFrame, customers: pd.DataFrame
) -> dict[str, object]:
    """Model treatment-arm activation among eligible customers; association only."""
    data = assignments.merge(
        outcomes[["experiment_id", "customer_id", "first_week_activation"]],
        on=["experiment_id", "customer_id"],
        how="inner",
    )
    data = data.merge(
        customers[
            [
                "customer_id",
                "acquisition_channel",
                "initial_segment",
                "account_funded",
                "onboarding_completed",
            ]
        ],
        on="customer_id",
        how="inner",
    )
    data = data[data["eligible"] & data["arm"].eq("treatment")].copy()
    data["assignment_date"] = pd.to_datetime(data["assignment_date"])
    split = temporal_split(data.rename(columns={"assignment_date": "feature_cutoff"}))
    features = ["acquisition_channel", "initial_segment", "account_funded", "onboarding_completed"]
    prep = ColumnTransformer(
        [
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                ["acquisition_channel", "initial_segment"],
            ),
            ("binary", "passthrough", ["account_funded", "onboarding_completed"]),
        ]
    )
    model = Pipeline(
        [("prep", prep), ("model", LogisticRegression(C=0.5, max_iter=500, random_state=1729))]
    )
    model.fit(split.train[features], split.train["first_week_activation"].astype(int))
    probabilities = pd.Series(
        model.predict_proba(split.test[features])[:, 1],
        index=split.test.index,
        name="response_probability",
    )
    return {
        "split": split,
        "features": features,
        "model": model,
        "probabilities": probabilities,
        "metrics": model_metrics(split.test["first_week_activation"], probabilities),
    }
