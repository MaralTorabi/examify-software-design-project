from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.errors import InvalidExamTransitionError
from core.types import ExamStateEnum

if TYPE_CHECKING:
    from core.schemas import AnswerSubmission, ExamResultReport


class ExamState(ABC):
    """Abstract State in the GoF State Pattern managing exam session lifecycle transitions."""

    @property
    @abstractmethod
    def state_enum(self) -> ExamStateEnum:
        """Returns the corresponding ExamStateEnum value."""
        ...

    @abstractmethod
    def start(self, context: Any, now: datetime) -> None:
        """Transitions exam from Created to InProgress."""
        ...

    @abstractmethod
    def submit_answer(
        self,
        context: Any,
        answer: AnswerSubmission,
        now: datetime,
    ) -> None:
        """Submits an answer while in InProgress state."""
        ...

    @abstractmethod
    def complete(self, context: Any, now: datetime) -> None:
        """Transitions exam from InProgress to Completed."""
        ...

    @abstractmethod
    def grade(
        self,
        context: Any,
        report: ExamResultReport,
        now: datetime,
    ) -> None:
        """Transitions exam from Completed to Graded."""
        ...


class CreatedState(ExamState):
    """Initial state: session is configured but student has not yet started answering questions."""

    @property
    def state_enum(self) -> ExamStateEnum:
        return ExamStateEnum.CREATED

    def start(self, context: Any, now: datetime) -> None:
        context.transition_to(InProgressState())

    def submit_answer(self, context: Any, answer: AnswerSubmission, now: datetime) -> None:
        raise InvalidExamTransitionError(
            "Cannot submit answers: exam session has not been started yet.",
            code="EXAM_NOT_STARTED",
        )

    def complete(self, context: Any, now: datetime) -> None:
        raise InvalidExamTransitionError(
            "Cannot complete exam session that has not been started.",
            code="INVALID_STATE_TRANSITION",
        )

    def grade(self, context: Any, report: ExamResultReport, now: datetime) -> None:
        raise InvalidExamTransitionError(
            "Cannot grade an exam session that has not been started or completed.",
            code="INVALID_STATE_TRANSITION",
        )


class InProgressState(ExamState):
    """Active exam state: student is iteratively receiving questions and submitting answers."""

    @property
    def state_enum(self) -> ExamStateEnum:
        return ExamStateEnum.IN_PROGRESS

    def start(self, context: Any, now: datetime) -> None:
        raise InvalidExamTransitionError(
            "Exam session is already in progress.",
            code="EXAM_ALREADY_IN_PROGRESS",
        )

    def submit_answer(self, context: Any, answer: AnswerSubmission, now: datetime) -> None:
        # Valid operation: answer submission is handled by the session context
        pass

    def complete(self, context: Any, now: datetime) -> None:
        context.transition_to(CompletedState())
        context.completed_at = now

    def grade(self, context: Any, report: ExamResultReport, now: datetime) -> None:
        raise InvalidExamTransitionError(
            "Exam session must be marked Completed before it can be Graded.",
            code="EXAM_NOT_COMPLETED",
        )


class CompletedState(ExamState):
    """Final examination state: all questions answered or session finished; awaiting final grading."""

    @property
    def state_enum(self) -> ExamStateEnum:
        return ExamStateEnum.COMPLETED

    def start(self, context: Any, now: datetime) -> None:
        raise InvalidExamTransitionError(
            "Cannot restart an already completed exam session.",
            code="EXAM_ALREADY_COMPLETED",
        )

    def submit_answer(self, context: Any, answer: AnswerSubmission, now: datetime) -> None:
        raise InvalidExamTransitionError(
            "Cannot submit answers: exam session is already completed.",
            code="EXAM_COMPLETED",
        )

    def complete(self, context: Any, now: datetime) -> None:
        # Idempotent or no-op
        pass

    def grade(self, context: Any, report: ExamResultReport, now: datetime) -> None:
        context.transition_to(GradedState())


class GradedState(ExamState):
    """Terminal state: exam is fully graded, report generated, and immutable."""

    @property
    def state_enum(self) -> ExamStateEnum:
        return ExamStateEnum.GRADED

    def start(self, context: Any, now: datetime) -> None:
        raise InvalidExamTransitionError(
            "Cannot restart an already graded exam session.",
            code="EXAM_ALREADY_GRADED",
        )

    def submit_answer(self, context: Any, answer: AnswerSubmission, now: datetime) -> None:
        raise InvalidExamTransitionError(
            "Cannot submit answers: exam session has already been graded.",
            code="EXAM_ALREADY_GRADED",
        )

    def complete(self, context: Any, now: datetime) -> None:
        raise InvalidExamTransitionError(
            "Exam session is already graded and sealed.",
            code="EXAM_ALREADY_GRADED",
        )

    def grade(self, context: Any, report: ExamResultReport, now: datetime) -> None:
        raise InvalidExamTransitionError(
            "Exam session has already been graded.",
            code="EXAM_ALREADY_GRADED",
        )


def state_from_enum(state_enum: ExamStateEnum) -> ExamState:
    """Instantiates concrete state object corresponding to ExamStateEnum."""
    mapping = {
        ExamStateEnum.CREATED: CreatedState,
        ExamStateEnum.IN_PROGRESS: InProgressState,
        ExamStateEnum.COMPLETED: CompletedState,
        ExamStateEnum.GRADED: GradedState,
    }
    state_cls = mapping.get(state_enum)
    if not state_cls:
        raise ValueError(f"Unknown ExamStateEnum value: {state_enum}")
    return state_cls()
