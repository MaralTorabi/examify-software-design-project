
from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from core.schemas import (
    ExamResultReport,
    PracticeRecommendation,
    QuestionPayload,
    QuestionSourceMeta,
    TopicPerformance,
)
from core.types import CompletionReason, Difficulty


class _ExamSessionLike(Protocol):
    """Minimum session contract required by analytics."""

    session_id: UUID
    student_id: UUID
    target_question_count: int
    current_difficulty: Difficulty
    completion_reason: CompletionReason


class _EvaluatedAnswer(Protocol):
    """An accepted answer paired with its original question."""

    question: QuestionPayload
    is_correct: bool


class AnalyticsService:
    """Builds an immutable performance report from evaluated answers."""

    WEAK_TOPIC_THRESHOLD = 0.60
    EASY_DIFFICULTY_THRESHOLD = 0.40
    RECOMMENDED_QUESTION_COUNT = 5
    MINIMUM_EVIDENCE_COUNT = 3

    @staticmethod
    def _unique_sources(
        sources: tuple[QuestionSourceMeta, ...] | list[QuestionSourceMeta],
    ) -> tuple[QuestionSourceMeta, ...]:
        """Keep the first citation for each document page."""

        result: list[QuestionSourceMeta] = []
        seen: set[tuple[UUID, int]] = set()

        for source in sources:
            key = (source.document_id, source.page_number)

            if key not in seen:
                seen.add(key)
                result.append(source)

        return tuple(result)

    def build_report(
        self,
        session: _ExamSessionLike,
        answers: tuple[_EvaluatedAnswer, ...],
        generated_at: datetime,
    ) -> ExamResultReport:
        """Build the final exam report without performing any I/O."""

        # Preserve topic insertion order for deterministic reports.
        topic_stats: dict[str, dict[str, object]] = {}

        correct_count = 0
        answered_count = len(answers)

        for answer in answers:
            if not isinstance(answer.is_correct, bool):
                raise TypeError("answer.is_correct must be a bool")

            question = answer.question
            topic = question.topic

            if topic not in topic_stats:
                topic_stats[topic] = {
                    "answered_count": 0,
                    "correct_count": 0,
                    "sources": [],
                    "incorrect_sources": [],
                }

            stats = topic_stats[topic]

            stats["answered_count"] = int(stats["answered_count"]) + 1

            sources = stats["sources"]
            assert isinstance(sources, list)
            sources.extend(question.sources)

            if answer.is_correct:
                correct_count += 1
                stats["correct_count"] = int(stats["correct_count"]) + 1
            else:
                incorrect_sources = stats["incorrect_sources"]
                assert isinstance(incorrect_sources, list)
                incorrect_sources.extend(question.sources)

        topic_performance: list[TopicPerformance] = []
        weak_topics: list[str] = []
        recommendations: list[PracticeRecommendation] = []

        for topic, stats in topic_stats.items():
            topic_answered = int(stats["answered_count"])
            topic_correct = int(stats["correct_count"])

            accuracy = topic_correct / topic_answered
            insufficient_evidence = (
                topic_answered < self.MINIMUM_EVIDENCE_COUNT
            )

            all_sources = stats["sources"]
            assert isinstance(all_sources, list)

            topic_sources = self._unique_sources(all_sources)

            topic_performance.append(
                TopicPerformance(
                    topic=topic,
                    answered_count=topic_answered,
                    correct_count=topic_correct,
                    accuracy=accuracy,
                    insufficient_evidence=insufficient_evidence,
                    sources=topic_sources,
                )
            )

            # A topic is weak only when there is sufficient evidence
            # and accuracy is strictly below 60%.
            if (
                not insufficient_evidence
                and accuracy < self.WEAK_TOPIC_THRESHOLD
            ):
                weak_topics.append(topic)

                incorrect_sources = stats["incorrect_sources"]
                assert isinstance(incorrect_sources, list)

                recommendation_sources = self._unique_sources(
                    incorrect_sources
                )

                suggested_difficulty = (
                    Difficulty.EASY
                    if accuracy < self.EASY_DIFFICULTY_THRESHOLD
                    else Difficulty.MEDIUM
                )

                recommendations.append(
                    PracticeRecommendation(
                        topic=topic,
                        reason=(
                            f"Topic accuracy is {accuracy:.0%} "
                            f"across {topic_answered} accepted answers."
                        ),
                        suggested_difficulty=suggested_difficulty,
                        recommended_question_count=(
                            self.RECOMMENDED_QUESTION_COUNT
                        ),
                        sources=recommendation_sources,
                    )
                )

        score_ratio = (
            correct_count / answered_count
            if answered_count > 0
            else None
        )

        return ExamResultReport(
            session_id=session.session_id,
            student_id=session.student_id,
            state="Graded",
            completion_reason=session.completion_reason,
            target_question_count=session.target_question_count,
            answered_count=answered_count,
            correct_count=correct_count,
            score_ratio=score_ratio,
            final_difficulty=session.current_difficulty,
            topic_performance=tuple(topic_performance),
            weak_topics=tuple(weak_topics),
            recommendations=tuple(recommendations),
            generated_at=generated_at,
        )
