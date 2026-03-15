"""
Accuracy Scorer — Calculates weighted final score (0-100).
Works with the new pipeline data flow (pass rates and raw scores).
"""

from typing import Any, Optional

from loguru import logger

from config import WEIGHTS, CONFIDENCE_THRESHOLD


class AccuracyScorer:
    """
    Calculates weighted final score from validation outputs.
    Uses weights from config.py.
    """

    def __init__(self, weights: Optional[dict] = None):
        self.weights = weights or WEIGHTS

    def calculate_score(
        self,
        math_result: Any = None,
        hallucination_result: Any = None,
        extraction_result: Any = None,
        validation_pass_rate: float = 100.0,
        hallucination_score: float = 100.0,
        completeness: float = 100.0,
        avg_confidence: float = 0.5,
    ) -> float:
        """
        Calculate the weighted final score (0-100).
        Accepts either raw scores or result objects.
        """
        # Use raw scores directly
        math_score = validation_pass_rate
        hall_score = hallucination_score
        comp_score = completeness
        conf_score = min(avg_confidence * 100, 100.0)  # Convert 0-1 → 0-100

        # Weighted final score
        final = (
            comp_score * self.weights.get("extraction_completeness", 0.30)
            + math_score * self.weights.get("math_validation", 0.35)
            + hall_score * self.weights.get("hallucination_score", 0.20)
            + conf_score * self.weights.get("confidence_score", 0.15)
        )

        logger.info(
            f"Score: Math={math_score:.1f}, Hall={hall_score:.1f}, "
            f"Comp={comp_score:.1f}, Conf={conf_score:.1f} → FINAL={final:.1f}"
        )

        return round(final, 2)
