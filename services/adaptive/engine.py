from __future__ import annotations

from uuid import UUID

from core.schemas import QuestionPayload
from core.types import Difficulty
from services.adaptive.strategies import (
    ConsecutiveAnswersStrategy,
    DifficultyStrategy,
    PerformanceSnapshot,
)

DIFFICULTY_RANK: dict[Difficulty, int] = {
    Difficulty.EASY: 1,
    Difficulty.MEDIUM: 2,
    Difficulty.HARD: 3,
}


class AdaptiveQuestionSelector:
    """Selects the next adaptive question from an available pool, handling difficulty matching and tie-breaking."""

    def __init__(self, strategy: DifficultyStrategy | None = None) -> None:
        self.strategy = strategy or ConsecutiveAnswersStrategy()

    def determine_next_difficulty(
        self,
        current_difficulty: Difficulty,
        recent_correctness: tuple[bool, ...],
    ) -> Difficulty:
        """Computes the target difficulty for the next question using the configured strategy."""
        snapshot = PerformanceSnapshot(
            answered_count=len(recent_correctness),
            recent_correctness=recent_correctness,
        )
        return self.strategy.next_difficulty(current_difficulty, snapshot)

    def select_next_question(
        self,
        pool: tuple[QuestionPayload, ...] | list[QuestionPayload],
        used_question_ids: set[UUID],
        target_difficulty: Difficulty,
    ) -> QuestionPayload | None:
        """Selects the next unused question matching target difficulty or nearest, breaking ties toward easier.

        Returns None if all questions in the pool have been used (pool exhausted).
        """
        available = [q for q in pool if q.question_id not in used_question_ids]
        if not available:
            return None

        # Exact match
        exact_matches = [q for q in available if q.difficulty == target_difficulty]
        if exact_matches:
            return exact_matches[0]

        target_rank = DIFFICULTY_RANK[target_difficulty]

        # Sort key:
        # 1. Primary: absolute distance from target rank
        # 2. Secondary (tie breaker): actual difficulty rank ascending (easier wins tie)
        best_question = min(
            available,
            key=lambda q: (
                abs(DIFFICULTY_RANK[q.difficulty] - target_rank),
                DIFFICULTY_RANK[q.difficulty],
            ),
        )
        return best_question
