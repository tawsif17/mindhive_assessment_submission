"""Small probability models used to rank catalogue candidates."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold


@dataclass
class ProbabilityRanker:
    """Logistic candidate ranker with optional out-of-sample calibration."""

    model: LogisticRegression
    calibrator: IsotonicRegression | None = None

    @classmethod
    def fit(cls, features: list[list[float]], labels: list[int]) -> "ProbabilityRanker":
        """Fit a deterministic model to named candidate features."""
        if len(set(labels)) < 2:
            raise ValueError("Candidate ranker needs positive and negative examples")
        model = LogisticRegression(
            C=1.0,
            class_weight="balanced",
            max_iter=2_000,
            random_state=17,
            solver="liblinear",
        )
        model.fit(np.asarray(features, dtype=float), np.asarray(labels, dtype=int))
        return cls(model=model)

    def predict(self, features: list[list[float]]) -> list[float]:
        """Return probabilities, passed through the calibration model when present."""
        if not features:
            return []
        raw = self.model.predict_proba(np.asarray(features, dtype=float))[:, 1]
        if self.calibrator is not None:
            raw = self.calibrator.predict(raw)
        return [float(max(0.0, min(1.0, value))) for value in raw]


def fit_ranker_with_group_calibration(
    features: list[list[float]],
    labels: list[int],
    groups: list[str],
) -> ProbabilityRanker:
    """Fit a ranker and calibrate it using inner grouped out-of-fold scores.

    The calibrator never sees a score produced by a model fitted on the same
    customer group. This keeps the confidence check separate from model fitting.
    """
    unique_groups = sorted(set(groups))
    if len(unique_groups) < 3 or len(set(labels)) < 2:
        return ProbabilityRanker.fit(features, labels)

    split_count = min(3, len(unique_groups))
    splitter = GroupKFold(n_splits=split_count)
    feature_array = np.asarray(features, dtype=float)
    label_array = np.asarray(labels, dtype=int)
    group_array = np.asarray(groups)
    calibration_scores: list[float] = []
    calibration_labels: list[int] = []

    for train_indexes, validation_indexes in splitter.split(
        feature_array, label_array, group_array
    ):
        fold_labels = label_array[train_indexes].tolist()
        if len(set(fold_labels)) < 2:
            continue
        fold_ranker = ProbabilityRanker.fit(
            feature_array[train_indexes].tolist(), fold_labels
        )
        fold_scores = fold_ranker.predict(feature_array[validation_indexes].tolist())
        calibration_scores.extend(fold_scores)
        calibration_labels.extend(label_array[validation_indexes].tolist())

    final_ranker = ProbabilityRanker.fit(features, labels)
    if len(calibration_scores) >= 20 and len(set(calibration_labels)) == 2:
        calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        calibrator.fit(calibration_scores, calibration_labels)
        final_ranker.calibrator = calibrator
    return final_ranker

