
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from core.schemas import QuestionPayload, QuestionSourceMeta
from core.types import CompletionReason, Difficulty
from domain.analytics.analytics_service import AnalyticsService

NOW = datetime.now(UTC)


@dataclass(frozen=True)
class FakeSession:
    session_id: UUID
    student_id: UUID
    target_question_count: int
    current_difficulty: Difficulty
    completion_reason: CompletionReason


@dataclass(frozen=True)
class FakeEvaluatedAnswer:
    question: QuestionPayload
    is_correct: bool


def make_answer(
    topic: str,
    is_correct: bool,
    page_number: int,
    document_id: UUID,
) -> FakeEvaluatedAnswer:
    source = QuestionSourceMeta(
        document_id=document_id,
        page_number=page_number,
        excerpt=f"Source content from page {page_number}.",
    )

    question = QuestionPayload(
        question_id=uuid4(),
        prompt=f"Question about {topic}?",
        options=("Option A", "Option B"),
        correct_index=0,
        difficulty=Difficulty.MEDIUM,
        explanation="Test explanation.",
        topic=topic,
        sources=(source,),
        generation_mode="mock",
        provider="test",
        created_at=NOW,
    )

    return FakeEvaluatedAnswer(
        question=question,
        is_correct=is_correct,
    )


def make_session(target_count: int = 10) -> FakeSession:
    return FakeSession(
        session_id=uuid4(),
        student_id=uuid4(),
        target_question_count=target_count,
        current_difficulty=Difficulty.HARD,
        completion_reason=CompletionReason.TARGET_REACHED,
    )


def test_build_report_calculates_score_and_weak_topics() -> None:
    document_id = uuid4()

    answers = (
        make_answer("Algebra", False, 1, document_id),
        make_answer("Algebra", False, 2, document_id),
        make_answer("Algebra", False, 3, document_id),
        make_answer("Algebra", True, 4, document_id),
        make_answer("Geometry", True, 5, document_id),
        make_answer("Geometry", True, 6, document_id),
        make_answer("Geometry", True, 7, document_id),
    )

    report = AnalyticsService().build_report(
        session=make_session(),
        answers=answers,
        generated_at=NOW,
    )

    assert report.answered_count == 7
    assert report.correct_count == 4
    assert report.score_ratio == 4 / 7

    assert report.weak_topics == ("Algebra",)

    algebra = report.topic_performance[0]

    assert algebra.topic == "Algebra"
    assert algebra.answered_count == 4
    assert algebra.correct_count == 1
    assert algebra.accuracy == 0.25
    assert algebra.insufficient_evidence is False

    assert len(report.recommendations) == 1
    assert report.recommendations[0].topic == "Algebra"
    assert report.recommendations[0].suggested_difficulty == Difficulty.EASY
    assert report.recommendations[0].recommended_question_count == 5


def test_recommendations_prioritize_incorrect_answer_sources() -> None:
    document_id = uuid4()

    answers = (
        make_answer("Databases", True, 1, document_id),
        make_answer("Databases", False, 2, document_id),
        make_answer("Databases", False, 3, document_id),
        make_answer("Databases", False, 4, document_id),
    )

    report = AnalyticsService().build_report(
        session=make_session(),
        answers=answers,
        generated_at=NOW,
    )

    recommendation = report.recommendations[0]

    recommended_pages = tuple(
        source.page_number for source in recommendation.sources
    )

    assert recommended_pages == (2, 3, 4)


def test_exactly_sixty_percent_is_not_a_weak_topic() -> None:
    document_id = uuid4()

    answers = (
        make_answer("Networks", True, 1, document_id),
        make_answer("Networks", True, 2, document_id),
        make_answer("Networks", True, 3, document_id),
        make_answer("Networks", False, 4, document_id),
        make_answer("Networks", False, 5, document_id),
    )

    report = AnalyticsService().build_report(
        session=make_session(),
        answers=answers,
        generated_at=NOW,
    )

    assert report.topic_performance[0].accuracy == 0.60
    assert report.weak_topics == ()
    assert report.recommendations == ()


def test_fewer_than_three_answers_means_insufficient_evidence() -> None:
    document_id = uuid4()

    answers = (
        make_answer("Operating Systems", False, 1, document_id),
        make_answer("Operating Systems", False, 2, document_id),
    )

    report = AnalyticsService().build_report(
        session=make_session(),
        answers=answers,
        generated_at=NOW,
    )

    performance = report.topic_performance[0]

    assert performance.answered_count == 2
    assert performance.insufficient_evidence is True
    assert report.weak_topics == ()
    assert report.recommendations == ()


def test_accuracy_at_forty_percent_recommends_medium() -> None:
    document_id = uuid4()

    answers = (
        make_answer("Security", True, 1, document_id),
        make_answer("Security", True, 2, document_id),
        make_answer("Security", False, 3, document_id),
        make_answer("Security", False, 4, document_id),
        make_answer("Security", False, 5, document_id),
    )

    report = AnalyticsService().build_report(
        session=make_session(),
        answers=answers,
        generated_at=NOW,
    )

    assert report.topic_performance[0].accuracy == 0.40
    assert report.weak_topics == ("Security",)
    assert report.recommendations[0].suggested_difficulty == Difficulty.MEDIUM


def test_empty_exam_has_null_score_ratio() -> None:
    report = AnalyticsService().build_report(
        session=make_session(),
        answers=(),
        generated_at=NOW,
    )

    assert report.answered_count == 0
    assert report.correct_count == 0
    assert report.score_ratio is None
    assert report.topic_performance == ()
    assert report.weak_topics == ()
    assert report.recommendations == ()
