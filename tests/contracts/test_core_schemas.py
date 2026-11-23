from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from core.errors import (
    InsufficientSourceContentError,
    format_error_envelope,
)
from core.errors import (
    ValidationError as DomainValidationError,
)
from core.schemas import (
    AnswerReceipt,
    AnswerSubmission,
    DocumentOut,
    ExamCreateRequest,
    ExamResultReport,
    ExamSessionOut,
    ExtractedPage,
    GenerationBatch,
    GenerationRequest,
    PracticeRecommendation,
    QuestionPayload,
    QuestionSourceMeta,
    StudentQuestionView,
    TokenResponse,
    TopicPerformance,
    UserCreate,
    UserOut,
)
from core.types import (
    CompletionReason,
    Difficulty,
    DocumentStatus,
    ExamMode,
    ExamStateEnum,
    Role,
)
from services.ai.adapter import AIAdapter, FallbackPolicy
from services.ai.fallback_adapter import FallbackAIAdapter
from services.ai.generation_service import QuestionGenerationService
from services.ai.mock_adapter import OfflineMockAIAdapter
from services.ai.validation import QuestionValidator

# ============================================================================
# 1. CORE SCHEMAS & POSITIVE DTO CONTRACT TESTS
# ============================================================================


def test_user_create_and_out_valid() -> None:
    uc = UserCreate(email="student@example.com", password="securepassword123", role=Role.STUDENT)
    assert uc.email == "student@example.com"
    assert uc.role == Role.STUDENT

    uo = UserOut(
        id=uuid4(),
        email="instructor@example.com",
        role=Role.INSTRUCTOR,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    assert uo.role == Role.INSTRUCTOR
    assert uo.is_active is True


def test_token_response_valid() -> None:
    token = TokenResponse(access_token="valid.jwt.token", token_type="bearer")
    assert token.access_token == "valid.jwt.token"
    assert token.token_type == "bearer"


def test_document_out_valid_lifecycle() -> None:
    doc_id = uuid4()
    now = datetime.now(UTC)
    sha = "a" * 64

    # Uploaded state
    d1 = DocumentOut(
        document_id=doc_id,
        filename="lecture1.pdf",
        sha256=sha,
        size_bytes=1024,
        status=DocumentStatus.UPLOADED,
        uploaded_at=now,
    )
    assert d1.status == DocumentStatus.UPLOADED

    # Ready state
    d2 = DocumentOut(
        document_id=doc_id,
        filename="lecture1.pdf",
        sha256=sha,
        size_bytes=1024,
        status=DocumentStatus.READY,
        page_count=5,
        extracted_page_count=5,
        uploaded_at=now,
    )
    assert d2.status == DocumentStatus.READY
    assert d2.extracted_page_count == 5

    # Failed state
    d3 = DocumentOut(
        document_id=doc_id,
        filename="corrupted.pdf",
        sha256=sha,
        size_bytes=1024,
        status=DocumentStatus.FAILED,
        error_code="ENCRYPTED_PDF",
        uploaded_at=now,
    )
    assert d3.status == DocumentStatus.FAILED
    assert d3.error_code == "ENCRYPTED_PDF"


def test_question_payload_valid() -> None:
    doc_id = uuid4()
    q_id = uuid4()
    source = QuestionSourceMeta(
        document_id=doc_id,
        page_number=1,
        excerpt="The modular monolith keeps internal boundaries sharp.",
    )
    payload = QuestionPayload(
        question_id=q_id,
        prompt="What is a primary benefit of a modular monolith?",
        options=(
            "It eliminates need for tests",
            "It keeps internal boundaries sharp",
            "It requires multiple databases",
        ),
        correct_index=1,
        difficulty=Difficulty.MEDIUM,
        explanation="Page 1 confirms sharp boundaries.",
        topic="Software Architecture",
        sources=(source,),
        generation_mode="mock",
        provider="test-mock",
        created_at=datetime.now(UTC),
    )
    assert payload.correct_index == 1
    assert payload.options[payload.correct_index] == "It keeps internal boundaries sharp"


def test_student_question_view_redaction() -> None:
    doc_id = uuid4()
    q_id = uuid4()
    source = QuestionSourceMeta(
        document_id=doc_id,
        page_number=1,
        excerpt="Confidential source text",
    )
    payload = QuestionPayload(
        question_id=q_id,
        prompt="Sample prompt?",
        options=("Option A", "Option B"),
        correct_index=0,
        difficulty=Difficulty.EASY,
        explanation="Secret instructor explanation",
        topic="Security",
        sources=(source,),
        generation_mode="mock",
        provider="test-mock",
        created_at=datetime.now(UTC),
    )

    view = StudentQuestionView.from_payload(payload, sequence_number=2)

    # 1. Verification of fields presence
    assert view.question_id == q_id
    assert view.sequence_number == 2
    assert view.prompt == payload.prompt
    assert view.options == payload.options

    # 2. Strict omission of sensitive attributes
    assert not hasattr(view, "correct_index")
    assert not hasattr(view, "explanation")
    assert not hasattr(view, "sources")
    assert "correct_index" not in StudentQuestionView.model_fields
    assert "explanation" not in StudentQuestionView.model_fields
    assert "sources" not in StudentQuestionView.model_fields

    # 3. Forbidding extra fields when initializing directly
    with pytest.raises(PydanticValidationError):
        StudentQuestionView(
            question_id=q_id,
            sequence_number=1,
            prompt="Prompt",
            options=("A", "B"),
            difficulty=Difficulty.EASY,
            topic="Test",
            correct_index=0,  # Must be rejected by extra='forbid'
        )


def test_exam_result_report_complete_validation() -> None:
    doc_id = uuid4()
    source = QuestionSourceMeta(document_id=doc_id, page_number=2, excerpt="Performance concept")

    t1 = TopicPerformance(
        topic="Concurrency",
        answered_count=4,
        correct_count=1,
        accuracy=0.25,
        insufficient_evidence=False,
        sources=(source,),
    )
    t2 = TopicPerformance(
        topic="Data Structures",
        answered_count=4,
        correct_count=4,
        accuracy=1.0,
        insufficient_evidence=False,
        sources=(source,),
    )
    rec = PracticeRecommendation(
        topic="Concurrency",
        reason="Accuracy below 60%",
        suggested_difficulty=Difficulty.EASY,
        recommended_question_count=5,
        sources=(source,),
    )

    report = ExamResultReport(
        session_id=uuid4(),
        student_id=uuid4(),
        state="Graded",
        completion_reason=CompletionReason.TARGET_REACHED,
        target_question_count=8,
        answered_count=8,
        correct_count=5,
        score_ratio=0.625,
        final_difficulty=Difficulty.MEDIUM,
        topic_performance=(t1, t2),
        weak_topics=("Concurrency",),
        recommendations=(rec,),
        generated_at=datetime.now(UTC),
    )
    assert report.score_ratio == 0.625
    assert report.weak_topics == ("Concurrency",)


# ============================================================================
# 2. NEGATIVE SCHEMA VALIDATION INVARIANTS
# ============================================================================


def test_question_payload_out_of_bounds_correct_index() -> None:
    doc_id = uuid4()
    source = QuestionSourceMeta(document_id=doc_id, page_number=1, excerpt="Valid text")
    with pytest.raises(PydanticValidationError) as exc:
        QuestionPayload(
            question_id=uuid4(),
            prompt="Prompt",
            options=("Option 1", "Option 2"),
            correct_index=2,  # Invalid: len is 2, index 2 is out of range
            difficulty=Difficulty.EASY,
            explanation="Explanation",
            topic="Topic",
            sources=(source,),
            generation_mode="mock",
            provider="mock",
            created_at=datetime.now(UTC),
        )
    assert "correct_index is outside options" in str(exc.value)


def test_question_payload_duplicate_options_rejected() -> None:
    doc_id = uuid4()
    source = QuestionSourceMeta(document_id=doc_id, page_number=1, excerpt="Valid text")
    with pytest.raises(PydanticValidationError) as exc:
        QuestionPayload(
            question_id=uuid4(),
            prompt="Prompt",
            options=("Option A", " option a ", "Option C"),  # Duplicate casefold
            correct_index=0,
            difficulty=Difficulty.EASY,
            explanation="Explanation",
            topic="Topic",
            sources=(source,),
            generation_mode="mock",
            provider="mock",
            created_at=datetime.now(UTC),
        )
    assert "options must be distinct" in str(exc.value)


def test_question_payload_multiple_documents_rejected() -> None:
    s1 = QuestionSourceMeta(document_id=uuid4(), page_number=1, excerpt="Text 1")
    s2 = QuestionSourceMeta(document_id=uuid4(), page_number=2, excerpt="Text 2")
    with pytest.raises(PydanticValidationError) as exc:
        QuestionPayload(
            question_id=uuid4(),
            prompt="Prompt",
            options=("A", "B"),
            correct_index=0,
            difficulty=Difficulty.EASY,
            explanation="Explanation",
            topic="Topic",
            sources=(s1, s2),  # Cites two distinct document IDs
            generation_mode="mock",
            provider="mock",
            created_at=datetime.now(UTC),
        )
    assert "baseline questions must cite one document" in str(exc.value)


def test_document_out_inconsistent_page_counts() -> None:
    with pytest.raises(PydanticValidationError) as exc:
        DocumentOut(
            document_id=uuid4(),
            filename="test.pdf",
            sha256="b" * 64,
            size_bytes=500,
            status=DocumentStatus.PROCESSING,
            page_count=3,
            extracted_page_count=5,  # Invalid: extracted > page_count
            uploaded_at=datetime.now(UTC),
        )
    assert "extracted_page_count cannot exceed page_count" in str(exc.value)


def test_frozen_immutability() -> None:
    user = UserCreate(email="test@example.com", password="password123")
    with pytest.raises(PydanticValidationError):
        # Direct mutation must fail on frozen model
        user.email = "modified@example.com"  # type: ignore[misc]


def test_error_envelope_formatter() -> None:
    env = format_error_envelope(
        code="NOT_FOUND",
        message="Resource was not located",
        request_id="req-987",
    )
    assert env == {
        "error": {
            "code": "NOT_FOUND",
            "message": "Resource was not located",
            "request_id": "req-987",
        }
    }


# ============================================================================
# 3. AI SUBSYSTEM & 3-STAGE VALIDATION TESTS
# ============================================================================


@pytest.mark.anyio
async def test_offline_mock_ai_adapter_deterministic() -> None:
    doc_id = uuid4()
    p1 = ExtractedPage(
        document_id=doc_id,
        page_number=1,
        text=(
            "Software architecture defines the structural design of computer systems. "
            "Modular monoliths organize code into strictly bounded internal packages. "
            "Layered architectures prevent circular dependency cycles effectively."
        ),
    )
    p2 = ExtractedPage(
        document_id=doc_id,
        page_number=2,
        text=(
            "Contract tests verify that serialized data transfer objects match interfaces. "
            "Pydantic schemas enforce runtime validation and strict immutability rules. "
            "Deterministic algorithms ensure reproducibility across regression test suites."
        ),
    )
    req = GenerationRequest(
        document_id=doc_id,
        pages=(p1, p2),
        question_count=3,
        difficulty=Difficulty.MEDIUM,
        seed=42,
    )

    adapter = OfflineMockAIAdapter()
    batch1 = await adapter.generate_questions(req)
    batch2 = await adapter.generate_questions(req)

    assert len(batch1.questions) == 3
    assert len(batch2.questions) == 3
    assert batch1.generation_mode == "mock"

    # Seed reproducibility check
    for q1, q2 in zip(batch1.questions, batch2.questions, strict=False):
        assert q1.question_id == q2.question_id
        assert q1.prompt == q2.prompt
        assert q1.options == q2.options
        assert q1.correct_index == q2.correct_index
        assert q1.sources == q2.sources

    # 3-Stage validation must succeed completely for mock output
    QuestionValidator.validate_batch(batch1, req.pages)


@pytest.mark.anyio
async def test_offline_mock_insufficient_content_raises() -> None:
    doc_id = uuid4()
    empty_page = ExtractedPage(document_id=doc_id, page_number=1, text="   \n\t  ")
    req = GenerationRequest(
        document_id=doc_id,
        pages=(empty_page,),
        question_count=2,
        seed=1,
    )
    adapter = OfflineMockAIAdapter()
    with pytest.raises(InsufficientSourceContentError):
        await adapter.generate_questions(req)


def test_validator_detects_ungrounded_excerpt() -> None:
    doc_id = uuid4()
    page = ExtractedPage(
        document_id=doc_id,
        page_number=1,
        text="The speed of light in vacuum is approximately 299,792 kilometers per second.",
    )
    fake_source = QuestionSourceMeta(
        document_id=doc_id,
        page_number=1,
        excerpt="Fabricated sentence that does not exist on page 1.",
    )
    question = QuestionPayload(
        question_id=uuid4(),
        prompt="Sample prompt?",
        options=("True", "False"),
        correct_index=0,
        difficulty=Difficulty.EASY,
        explanation="Expl",
        topic="Physics",
        sources=(fake_source,),
        generation_mode="live",
        provider="mock",
        created_at=datetime.now(UTC),
    )

    with pytest.raises(DomainValidationError) as exc:
        QuestionValidator.validate_question(question, (page,))
    assert "excerpt does not match the extracted text" in str(exc.value)


def test_validator_detects_out_of_bounds_page_citation() -> None:
    doc_id = uuid4()
    page = ExtractedPage(
        document_id=doc_id,
        page_number=1,
        text="Page 1 text content.",
    )
    out_of_bounds_source = QuestionSourceMeta(
        document_id=doc_id,
        page_number=99,  # Document has only page 1
        excerpt="Page 1 text content.",
    )
    question = QuestionPayload(
        question_id=uuid4(),
        prompt="Sample prompt?",
        options=("True", "False"),
        correct_index=0,
        difficulty=Difficulty.EASY,
        explanation="Expl",
        topic="General",
        sources=(out_of_bounds_source,),
        generation_mode="live",
        provider="mock",
        created_at=datetime.now(UTC),
    )

    with pytest.raises(DomainValidationError) as exc:
        QuestionValidator.validate_question(question, (page,))
    assert "cited page 99 does not exist" in str(exc.value)


# ============================================================================
# 4. FALLBACK ADAPTER & GENERATION SERVICE INTEGRATION
# ============================================================================


class FailingPrimaryAdapter(AIAdapter):
    """Simulates a remote LLM adapter encountering a network timeout."""

    async def generate_questions(self, request: GenerationRequest) -> GenerationBatch:
        raise ConnectionError("Remote AI provider timed out after 30s")


class ProgrammingBugPrimaryAdapter(AIAdapter):
    """Simulates a primary adapter with an unrecoverable code bug."""

    async def generate_questions(self, request: GenerationRequest) -> GenerationBatch:
        raise TypeError("Unexpected NoneType in response parser")


@pytest.mark.anyio
async def test_fallback_adapter_recovers_from_network_error() -> None:
    doc_id = uuid4()
    page = ExtractedPage(
        document_id=doc_id,
        page_number=1,
        text=(
            "Adaptive examination dynamically matches question difficulty to student capability. "
            "Continuous difficulty adjustments optimize assessment precision across test sessions."
        ),
    )
    req = GenerationRequest(
        document_id=doc_id,
        pages=(page,),
        question_count=1,
        seed=77,
    )

    primary = FailingPrimaryAdapter()
    fallback = OfflineMockAIAdapter()
    adapter = FallbackAIAdapter(
        primary=primary,
        fallback=fallback,
        policy=FallbackPolicy(allow_mock_fallback=True),
    )

    service = QuestionGenerationService(adapter=adapter)
    batch = await service.generate(actor_id=uuid4(), request=req)

    assert len(batch.questions) == 1
    assert batch.generation_mode == "mock"
    assert batch.fallback_reason is not None
    assert "ConnectionError" in batch.fallback_reason
    assert any("Fallback activated" in w for w in batch.warnings)


@pytest.mark.anyio
async def test_fallback_adapter_propagates_programming_error() -> None:
    doc_id = uuid4()
    page = ExtractedPage(
        document_id=doc_id,
        page_number=1,
        text="Valid text passage.",
    )
    req = GenerationRequest(
        document_id=doc_id,
        pages=(page,),
        question_count=1,
    )

    primary = ProgrammingBugPrimaryAdapter()
    fallback = OfflineMockAIAdapter()
    adapter = FallbackAIAdapter(
        primary=primary,
        fallback=fallback,
        policy=FallbackPolicy(allow_mock_fallback=True),
    )

    service = QuestionGenerationService(adapter=adapter)
    # Per Section 3.1: Programming errors must be propagated, never masked as mock output
    with pytest.raises(TypeError):
        await service.generate(actor_id=uuid4(), request=req)


# ============================================================================
# 5. EXAM LIFECYCLE & ANSWER SCHEMA CONTRACT TESTS
# ============================================================================


def test_exam_create_and_session_out() -> None:
    doc_id = uuid4()
    student_id = uuid4()
    session_id = uuid4()
    now = datetime.now(UTC)

    create_req = ExamCreateRequest(
        document_id=doc_id,
        target_question_count=15,
        initial_difficulty=Difficulty.MEDIUM,
        mode=ExamMode.PRACTICE,
    )
    assert create_req.target_question_count == 15
    assert create_req.mode == ExamMode.PRACTICE

    session_out = ExamSessionOut(
        session_id=session_id,
        student_id=student_id,
        document_id=doc_id,
        state=ExamStateEnum.IN_PROGRESS,
        mode=ExamMode.PRACTICE,
        target_question_count=15,
        current_question_sequence=3,
        current_difficulty=Difficulty.MEDIUM,
        created_at=now,
    )
    assert session_out.state == ExamStateEnum.IN_PROGRESS
    assert session_out.current_question_sequence == 3


def test_answer_submission_and_receipt() -> None:
    sub_id = uuid4()
    sess_id = uuid4()
    q_id = uuid4()

    sub = AnswerSubmission(
        submission_id=sub_id,
        session_id=sess_id,
        question_id=q_id,
        selected_index=2,
    )
    assert sub.selected_index == 2

    receipt = AnswerReceipt(
        submission_id=sub_id,
        session_id=sess_id,
        question_id=q_id,
        is_correct=True,
        correct_index=2,
        explanation="Direct text match on page 1.",
        next_difficulty=Difficulty.HARD,
        exam_completed=False,
    )
    assert receipt.is_correct is True
    assert receipt.next_difficulty == Difficulty.HARD


def test_source_meta_requires_1_indexed_page() -> None:
    doc_id = uuid4()
    # 1-indexed: page 0 must be rejected
    with pytest.raises(PydanticValidationError):
        QuestionSourceMeta(
            document_id=doc_id,
            page_number=0,
            excerpt="Invalid 0-indexed page",
        )

    # 1-indexed: negative page must be rejected
    with pytest.raises(PydanticValidationError):
        QuestionSourceMeta(
            document_id=doc_id,
            page_number=-1,
            excerpt="Invalid negative page",
        )

    # ExtractedPage page_number must also be positive int
    with pytest.raises(PydanticValidationError):
        ExtractedPage(
            document_id=doc_id,
            page_number=0,
            text="Text",
        )


def test_topic_performance_validation_rules() -> None:
    doc_id = uuid4()
    source = QuestionSourceMeta(document_id=doc_id, page_number=1, excerpt="Concept text")

    # Inconsistent accuracy vs counts
    with pytest.raises(PydanticValidationError):
        TopicPerformance(
            topic="Math",
            answered_count=4,
            correct_count=2,
            accuracy=0.80,  # Should be 0.50
            insufficient_evidence=False,
            sources=(source,),
        )

    # Inconsistent insufficient_evidence flag (answered_count < 3 must be True)
    with pytest.raises(PydanticValidationError):
        TopicPerformance(
            topic="Math",
            answered_count=2,
            correct_count=1,
            accuracy=0.50,
            insufficient_evidence=False,  # Must be True since count < 3
            sources=(source,),
        )


@pytest.mark.anyio
async def test_question_generation_service_happy_path() -> None:
    doc_id = uuid4()
    actor_id = uuid4()
    page = ExtractedPage(
        document_id=doc_id,
        page_number=1,
        text=(
            "Microservices partition systems by bounded contexts. "
            "Modular monoliths provide identical boundary guarantees in a single deployment unit. "
            "Clean architectures decouple business rules from external frameworks."
        ),
    )
    req = GenerationRequest(
        document_id=doc_id,
        pages=(page,),
        question_count=2,
        seed=101,
    )

    service = QuestionGenerationService()
    batch = await service.generate(actor_id=actor_id, request=req)

    assert len(batch.questions) == 2
    assert batch.generation_mode == "mock"
    assert batch.fallback_reason is None
