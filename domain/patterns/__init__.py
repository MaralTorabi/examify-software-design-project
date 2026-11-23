"""GoF Design Pattern implementations: Factory Method and State Machine."""

from domain.patterns.exam_states import (
    CompletedState,
    CreatedState,
    ExamState,
    GradedState,
    InProgressState,
    state_from_enum,
)
from domain.patterns.question_factory import (
    MultipleChoiceQuestion,
    MultipleChoiceQuestionFactory,
    Question,
    QuestionFactory,
    QuestionSpec,
)

__all__ = [
    "QuestionFactory",
    "MultipleChoiceQuestionFactory",
    "QuestionSpec",
    "Question",
    "MultipleChoiceQuestion",
    "ExamState",
    "CreatedState",
    "InProgressState",
    "CompletedState",
    "GradedState",
    "state_from_enum",
]
