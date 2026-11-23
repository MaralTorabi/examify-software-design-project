from __future__ import annotations

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from core.types import (
    CompletionReason,
    Difficulty,
    DocumentStatus,
    ExamMode,
    ExamStateEnum,
    Role,
)

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
Ratio = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class FrozenContract(BaseModel):
    """Base class for all immutable, strictly validated Examify data transfer objects."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
    )


class UserCreate(FrozenContract):
    """Payload for registering or creating a new user."""

    email: NonEmptyText
    password: Annotated[str, StringConstraints(min_length=8)]
    role: Role = Role.STUDENT


class UserOut(FrozenContract):
    """Safe public representation of a user."""

    id: UUID
    email: NonEmptyText
    role: Role
    is_active: bool = True
    created_at: AwareDatetime


class TokenResponse(FrozenContract):
    """Authentication bearer token response."""

    access_token: NonEmptyText
    token_type: Literal["bearer"] = "bearer"


class ExtractedPage(FrozenContract):
    """Extracted text page from a physical PDF document, indexed starting at page 1."""

    document_id: UUID
    page_number: PositiveInt
    text: str


class DocumentOut(FrozenContract):
    """Metadata response representing an ingested document."""

    schema_version: Literal["1.0"] = "1.0"
    document_id: UUID
    filename: NonEmptyText
    sha256: Sha256
    size_bytes: PositiveInt
    status: DocumentStatus
    page_count: PositiveInt | None = None
    extracted_page_count: NonNegativeInt = 0
    uploaded_at: AwareDatetime
    warnings: tuple[NonEmptyText, ...] = ()
    error_code: NonEmptyText | None = None

    @model_validator(mode="after")
    def validate_processing_status(self) -> Self:
        if self.page_count is None:
            if self.extracted_page_count != 0:
                raise ValueError("extracted pages require a known page_count")
        elif self.extracted_page_count > self.page_count:
            raise ValueError("extracted_page_count cannot exceed page_count")

        if self.status == DocumentStatus.READY:
            if self.page_count is None:
                raise ValueError("Ready documents require page_count")
            if self.extracted_page_count < 1:
                raise ValueError("Ready documents require extractable text")

        if self.status == DocumentStatus.FAILED:
            if self.error_code is None:
                raise ValueError("Failed documents require error_code")
        elif self.error_code is not None:
            raise ValueError("error_code is valid only for Failed documents")

        return self


# Backward-compatible alias matching Section 4.2 of SOFTWARE_ARCHITECTURE.md
DocumentUploadResponse = DocumentOut


class QuestionSourceMeta(FrozenContract):
    """Traceable citation linking a question to a physical 1-indexed document page."""

    document_id: UUID
    page_number: PositiveInt
    excerpt: NonEmptyText


# Alias matching Section 4.2 of SOFTWARE_ARCHITECTURE.md
SourceMeta = QuestionSourceMeta


class QuestionPayload(FrozenContract):
    """Complete internal question model carrying answer keys and citation metadata."""

    schema_version: Literal["1.0"] = "1.0"
    question_id: UUID
    question_type: Literal["multiple_choice"] = "multiple_choice"
    prompt: NonEmptyText
    options: tuple[NonEmptyText, ...] = Field(min_length=2, max_length=6)
    correct_index: NonNegativeInt
    difficulty: Difficulty
    explanation: NonEmptyText
    topic: NonEmptyText
    sources: tuple[QuestionSourceMeta, ...] = Field(min_length=1)
    generation_mode: Literal["live", "mock"] = "mock"
    provider: NonEmptyText
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_question(self) -> Self:
        if self.correct_index >= len(self.options):
            raise ValueError("correct_index is outside options")

        normalized_options = tuple(" ".join(option.split()).casefold() for option in self.options)
        if len(set(normalized_options)) != len(normalized_options):
            raise ValueError("options must be distinct")

        document_ids = {source.document_id for source in self.sources}
        if len(document_ids) != 1:
            raise ValueError("baseline questions must cite one document")

        source_keys = {
            (source.document_id, source.page_number, source.excerpt) for source in self.sources
        }
        if len(source_keys) != len(self.sources):
            raise ValueError("duplicate source references")

        return self


class StudentQuestionView(FrozenContract):
    """Safe question model for students strictly omitting correct_index, explanation, and sources."""

    schema_version: Literal["1.0"] = "1.0"
    session_id: UUID | None = None
    question_id: UUID
    sequence_number: PositiveInt = 1
    prompt: NonEmptyText
    options: tuple[NonEmptyText, ...] = Field(min_length=2, max_length=6)
    difficulty: Difficulty
    topic: NonEmptyText

    @classmethod
    def from_payload(
        cls,
        payload: QuestionPayload,
        sequence_number: int = 1,
        session_id: UUID | None = None,
    ) -> StudentQuestionView:
        """Projects internal QuestionPayload into a redacted, leak-proof StudentQuestionView."""
        return cls(
            session_id=session_id,
            question_id=payload.question_id,
            sequence_number=sequence_number,
            prompt=payload.prompt,
            options=payload.options,
            difficulty=payload.difficulty,
            topic=payload.topic,
        )


class GenerationRequest(FrozenContract):
    """Request DTO passed to AI adapters to generate questions from extracted pages."""

    document_id: UUID
    pages: tuple[ExtractedPage, ...] = Field(min_length=1)
    question_count: PositiveInt = 5
    difficulty: Difficulty = Difficulty.MEDIUM
    language: NonEmptyText = "en"
    seed: int = 0


class GenerationBatch(FrozenContract):
    """Output batch returned by AI adapters after question generation."""

    questions: tuple[QuestionPayload, ...]
    generation_mode: Literal["live", "mock"]
    provider: NonEmptyText
    fallback_reason: NonEmptyText | None = None
    warnings: tuple[NonEmptyText, ...] = ()


class ExamCreateRequest(FrozenContract):
    """Request DTO to initiate a new adaptive exam session."""

    document_id: UUID
    target_question_count: PositiveInt = 10
    initial_difficulty: Difficulty = Difficulty.MEDIUM
    mode: ExamMode = ExamMode.PRACTICE


class ExamSessionOut(FrozenContract):
    """Exam session state representation for clients."""

    session_id: UUID
    student_id: UUID
    document_id: UUID
    state: ExamStateEnum
    mode: ExamMode
    target_question_count: PositiveInt
    current_question_sequence: NonNegativeInt = 0
    current_difficulty: Difficulty
    created_at: AwareDatetime
    completed_at: AwareDatetime | None = None


class AnswerSubmission(FrozenContract):
    """Student submission answering an issued question in an active exam session."""

    schema_version: Literal["1.0"] = "1.0"
    submission_id: UUID
    session_id: UUID
    question_id: UUID
    selected_index: NonNegativeInt


class AnswerReceipt(FrozenContract):
    """Receipt acknowledging an answer submission with score and progression details."""

    submission_id: UUID
    session_id: UUID
    question_id: UUID
    is_correct: bool
    correct_index: NonNegativeInt | None = None
    explanation: NonEmptyText | None = None
    next_difficulty: Difficulty | None = None
    exam_completed: bool = False


class TopicPerformance(FrozenContract):
    """Analyzed performance metrics for a specific topic within an exam session."""

    topic: NonEmptyText
    answered_count: PositiveInt
    correct_count: NonNegativeInt
    accuracy: Ratio
    insufficient_evidence: bool
    sources: tuple[QuestionSourceMeta, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.correct_count > self.answered_count:
            raise ValueError("correct_count cannot exceed answered_count")

        expected = self.correct_count / self.answered_count
        if abs(self.accuracy - expected) > 1e-9:
            raise ValueError("accuracy must equal correct_count / answered_count")

        if self.insufficient_evidence != (self.answered_count < 3):
            raise ValueError("insufficient_evidence must reflect the three-answer minimum")

        return self


class PracticeRecommendation(FrozenContract):
    """Targeted learning recommendation for weak topics based on exam performance."""

    topic: NonEmptyText
    reason: NonEmptyText
    suggested_difficulty: Difficulty
    recommended_question_count: PositiveInt
    sources: tuple[QuestionSourceMeta, ...] = Field(min_length=1)


class ExamResultReport(FrozenContract):
    """Comprehensive final graded report for a completed exam session."""

    schema_version: Literal["1.0"] = "1.0"
    session_id: UUID
    student_id: UUID
    state: Literal["Graded"] = "Graded"
    completion_reason: CompletionReason
    target_question_count: PositiveInt
    answered_count: NonNegativeInt
    correct_count: NonNegativeInt
    score_ratio: Ratio | None
    final_difficulty: Difficulty
    topic_performance: tuple[TopicPerformance, ...] = ()
    weak_topics: tuple[NonEmptyText, ...] = ()
    recommendations: tuple[PracticeRecommendation, ...] = ()
    generated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if self.answered_count > self.target_question_count:
            raise ValueError("answered_count cannot exceed target_question_count")
        if self.correct_count > self.answered_count:
            raise ValueError("correct_count cannot exceed answered_count")

        if self.answered_count == 0:
            if self.score_ratio is not None:
                raise ValueError("empty exams require score_ratio=None")
        else:
            expected = self.correct_count / self.answered_count
            if self.score_ratio is None:
                raise ValueError("answered exams require score_ratio")
            if abs(self.score_ratio - expected) > 1e-9:
                raise ValueError("score_ratio is inconsistent")

        topics = {item.topic: item for item in self.topic_performance}
        if len(topics) != len(self.topic_performance):
            raise ValueError("duplicate topic performance entries")

        if sum(item.answered_count for item in topics.values()) != self.answered_count:
            raise ValueError("topic answer totals are inconsistent")

        if sum(item.correct_count for item in topics.values()) != self.correct_count:
            raise ValueError("topic correct totals are inconsistent")

        expected_weak = {
            topic
            for topic, item in topics.items()
            if not item.insufficient_evidence and item.accuracy < 0.60
        }
        if (
            len(set(self.weak_topics)) != len(self.weak_topics)
            or set(self.weak_topics) != expected_weak
        ):
            raise ValueError("weak_topics are inconsistent")

        recommended_topics = tuple(item.topic for item in self.recommendations)
        if (
            len(set(recommended_topics)) != len(recommended_topics)
            or set(recommended_topics) != expected_weak
        ):
            raise ValueError("exactly one recommendation is required for each weak topic")

        return self
