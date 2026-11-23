from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from core.errors import ValidationError
from core.schemas import QuestionPayload, QuestionSourceMeta
from core.types import Difficulty


@dataclass(frozen=True)
class QuestionSpec:
    """Specification parameters required to instantiate and validate a domain question."""

    question_id: UUID
    document_id: UUID
    kind: Literal["multiple_choice", "true_false"]
    prompt: str
    options: tuple[str, ...]
    correct_index: int
    difficulty: Difficulty
    explanation: str
    topic: str
    sources: tuple[QuestionSourceMeta, ...]


@dataclass(frozen=True)
class Question:
    """Domain model representing a validated exam question."""

    question_id: UUID
    document_id: UUID
    kind: str
    prompt: str
    options: tuple[str, ...]
    correct_index: int
    difficulty: Difficulty
    explanation: str
    topic: str
    sources: tuple[QuestionSourceMeta, ...]


class MultipleChoiceQuestion(Question):
    """Concrete multiple-choice question carrying distinct options and answer key."""
    pass


class QuestionFactory(ABC):
    """GoF Factory Method defining the template construction and validation of exam questions."""

    def create(self, spec: QuestionSpec) -> Question:
        """Template method validating invariants before invoking the factory method."""
        self.validate(spec)
        return self.create_question(spec)

    @abstractmethod
    def validate(self, spec: QuestionSpec) -> None:
        """Validates specific question invariants."""
        ...

    @abstractmethod
    def create_question(self, spec: QuestionSpec) -> Question:
        """Factory method to construct concrete Question instance."""
        ...


class MultipleChoiceQuestionFactory(QuestionFactory):
    """Factory creating multiple choice questions with 2 to 6 distinct options and valid 0-based answer key."""

    def validate(self, spec: QuestionSpec) -> None:
        if not (2 <= len(spec.options) <= 6):
            raise ValidationError(
                f"Multiple choice questions require between 2 and 6 options; got {len(spec.options)}."
            )

        if not (0 <= spec.correct_index < len(spec.options)):
            raise ValidationError(
                f"correct_index {spec.correct_index} is out of bounds for {len(spec.options)} options."
            )

        normalized = tuple(" ".join(opt.split()).casefold() for opt in spec.options)
        if len(set(normalized)) != len(normalized):
            raise ValidationError("All options must be distinct.")

        if not spec.prompt.strip():
            raise ValidationError("Question prompt cannot be empty.")

        if not spec.sources:
            raise ValidationError("Question must have at least one source citation.")

    def create_question(self, spec: QuestionSpec) -> MultipleChoiceQuestion:
        return MultipleChoiceQuestion(
            question_id=spec.question_id,
            document_id=spec.document_id,
            kind="multiple_choice",
            prompt=spec.prompt.strip(),
            options=spec.options,
            correct_index=spec.correct_index,
            difficulty=spec.difficulty,
            explanation=spec.explanation.strip(),
            topic=spec.topic.strip(),
            sources=spec.sources,
        )

    def create_from_payload(self, payload: QuestionPayload) -> MultipleChoiceQuestion:
        """Convenience factory method constructing domain Question directly from QuestionPayload contract."""
        spec = QuestionSpec(
            question_id=payload.question_id,
            document_id=payload.sources[0].document_id,
            kind="multiple_choice",
            prompt=payload.prompt,
            options=payload.options,
            correct_index=payload.correct_index,
            difficulty=payload.difficulty,
            explanation=payload.explanation,
            topic=payload.topic,
            sources=payload.sources,
        )
        return self.create(spec)
