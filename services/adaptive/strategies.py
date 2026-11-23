from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.types import Difficulty


@dataclass(frozen=True)
class PerformanceSnapshot:
    """Snapshot of recent student performance in an active exam session."""

    answered_count: int
    recent_correctness: tuple[bool, ...]


class DifficultyStrategy(ABC):
    """Abstract Strategy interface for calculating the next question difficulty."""

    @abstractmethod
    def next_difficulty(
        self,
        current: Difficulty,
        performance: PerformanceSnapshot,
    ) -> Difficulty:
        """Determines the next difficulty level given the current difficulty and answer history."""
        ...


class ConsecutiveAnswersStrategy(DifficultyStrategy):
    """Adjusts difficulty based on consecutive correct or incorrect responses.

    Rules:
    - 2 consecutive correct answers -> promote difficulty (Easy -> Medium -> Hard)
    - 2 consecutive incorrect answers -> demote difficulty (Hard -> Medium -> Easy)
    - Otherwise -> maintain current difficulty.
    """

    def next_difficulty(
        self,
        current: Difficulty,
        performance: PerformanceSnapshot,
    ) -> Difficulty:
        recent = performance.recent_correctness
        if len(recent) < 2:
            return current

        # Check last 2 answers
        last_two = recent[-2:]
        if all(last_two):  # [True, True]
            if current == Difficulty.EASY:
                return Difficulty.MEDIUM
            if current == Difficulty.MEDIUM:
                return Difficulty.HARD
            return Difficulty.HARD

        if not any(last_two):  # [False, False]
            if current == Difficulty.HARD:
                return Difficulty.MEDIUM
            if current == Difficulty.MEDIUM:
                return Difficulty.EASY
            return Difficulty.EASY

        return current


class RollingAccuracyStrategy(DifficultyStrategy):
    """Adjusts difficulty based on rolling window accuracy thresholds.

    Rules:
    - Window size defaults to 5.
    - If window accuracy >= 0.80 -> promote difficulty.
    - If window accuracy <= 0.40 -> demote difficulty.
    - Otherwise -> maintain current difficulty.
    """

    def __init__(self, window_size: int = 5) -> None:
        self.window_size = window_size

    def next_difficulty(
        self,
        current: Difficulty,
        performance: PerformanceSnapshot,
    ) -> Difficulty:
        recent = performance.recent_correctness
        if not recent:
            return current

        window = recent[-self.window_size :]
        accuracy = sum(1 for correct in window if correct) / len(window)

        if accuracy >= 0.80:
            if current == Difficulty.EASY:
                return Difficulty.MEDIUM
            if current == Difficulty.MEDIUM:
                return Difficulty.HARD
            return Difficulty.HARD

        if accuracy <= 0.40:
            if current == Difficulty.HARD:
                return Difficulty.MEDIUM
            if current == Difficulty.MEDIUM:
                return Difficulty.EASY
            return Difficulty.EASY

        return current
