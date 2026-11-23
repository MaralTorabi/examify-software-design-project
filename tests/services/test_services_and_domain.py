from __future__ import annotations

import io
from datetime import UTC, datetime
from uuid import uuid4

import pypdf
import pytest

from core.errors import (
    ConflictError,
    InsufficientSourceContentError,
    InvalidExamTransitionError,
    ValidationError,
)
from core.schemas import (
    AnswerSubmission,
    ExamCreateRequest,
    QuestionPayload,
    QuestionSourceMeta,
    StudentQuestionView,
)
from core.types import (
    Difficulty,
    DocumentStatus,
    ExamMode,
    ExamStateEnum,
)
from domain.application.exam_service import ExamApplicationService
from domain.patterns.exam_states import (
    CompletedState,
    CreatedState,
    GradedState,
    InProgressState,
)
from domain.patterns.question_factory import (
    MultipleChoiceQuestionFactory,
    QuestionSpec,
)
from domain.persistence.database import init_db
from domain.persistence.models import (
    Base,
    DocumentModel,
    ExamSessionModel,
    QuestionModel,
    QuestionSourceModel,
    UserModel,
)
from domain.persistence.uow import SQLAlchemyUnitOfWork
from services.adaptive.engine import AdaptiveQuestionSelector
from services.adaptive.strategies import (
    ConsecutiveAnswersStrategy,
    PerformanceSnapshot,
    RollingAccuracyStrategy,
)
from services.ingestion.extractor import ContentExtractionService

# ============================================================================
# 1. INGESTION SERVICE TESTS (PASTED TEXT & BYTES)
# ============================================================================


def test_extraction_from_pasted_text() -> None:
    svc = ContentExtractionService()
    doc_id = uuid4()
    raw_text = (
        "First chapter of the book.\n\n"
        "Second paragraph with critical architectural definitions.\n\n"
        "Third paragraph concluding page one."
    )
    pages = svc.extract_from_text(doc_id, raw_text)
    assert len(pages) >= 1
    assert pages[0].document_id == doc_id
    assert pages[0].page_number == 1
    assert "First chapter" in pages[0].text


def test_extraction_from_pasted_text_page_breaks() -> None:
    svc = ContentExtractionService()
    doc_id = uuid4()
    raw_text = "Page 1 Content\x0cPage 2 Content\x0cPage 3 Content"
    pages = svc.extract_from_text(doc_id, raw_text)
    assert len(pages) == 3
    assert pages[0].page_number == 1
    assert pages[0].text == "Page 1 Content"
    assert pages[1].page_number == 2
    assert pages[1].text == "Page 2 Content"
    assert pages[2].page_number == 3
    assert pages[2].text == "Page 3 Content"


def test_extraction_from_text_empty_raises() -> None:
    svc = ContentExtractionService()
    with pytest.raises(InsufficientSourceContentError):
        svc.extract_from_text(uuid4(), "   \n\t  ")


def test_extraction_from_bytes_txt() -> None:
    svc = ContentExtractionService()
    doc_id = uuid4()
    content = b"Sample text content from uploaded text file."
    pages = svc.extract_from_bytes(doc_id, "notes.txt", content)
    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert "Sample text content" in pages[0].text


def test_extraction_from_bytes_pdf() -> None:
    # Build in-memory PDF using pypdf writer
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    stream = io.BytesIO()
    writer.write(stream)
    pdf_bytes = stream.getvalue()

    svc = ContentExtractionService()
    doc_id = uuid4()
    # Blank PDF has no text -> should raise InsufficientSourceContentError
    with pytest.raises(InsufficientSourceContentError):
        svc.extract_from_bytes(doc_id, "blank.pdf", pdf_bytes)


def test_extraction_unsupported_extension_raises() -> None:
    svc = ContentExtractionService()
    with pytest.raises(ValidationError) as exc:
        svc.extract_from_bytes(uuid4(), "image.png", b"fake binary data")
    assert "Unsupported file format" in str(exc.value)


def test_sha256_computation() -> None:
    svc = ContentExtractionService()
    data = b"Examify Verification Bytes"
    h1 = svc.compute_sha256(data)
    assert len(h1) == 64
    assert h1 == svc.compute_sha256(data)


# ============================================================================
# 2. ADAPTIVE DIFFICULTY STRATEGIES & QUESTION SELECTOR TESTS
# ============================================================================


def test_consecutive_answers_strategy() -> None:
    strat = ConsecutiveAnswersStrategy()

    # 2 consecutive correct -> promote
    snap_promote = PerformanceSnapshot(answered_count=2, recent_correctness=(True, True))
    assert strat.next_difficulty(Difficulty.EASY, snap_promote) == Difficulty.MEDIUM
    assert strat.next_difficulty(Difficulty.MEDIUM, snap_promote) == Difficulty.HARD
    assert strat.next_difficulty(Difficulty.HARD, snap_promote) == Difficulty.HARD  # Upper bound

    # 2 consecutive incorrect -> demote
    snap_demote = PerformanceSnapshot(answered_count=2, recent_correctness=(False, False))
    assert strat.next_difficulty(Difficulty.HARD, snap_demote) == Difficulty.MEDIUM
    assert strat.next_difficulty(Difficulty.MEDIUM, snap_demote) == Difficulty.EASY
    assert strat.next_difficulty(Difficulty.EASY, snap_demote) == Difficulty.EASY  # Lower bound

    # Alternating -> maintain
    snap_alt = PerformanceSnapshot(answered_count=2, recent_correctness=(True, False))
    assert strat.next_difficulty(Difficulty.MEDIUM, snap_alt) == Difficulty.MEDIUM


def test_rolling_accuracy_strategy() -> None:
    strat = RollingAccuracyStrategy(window_size=5)

    # 4/5 = 80% -> promote
    snap_high = PerformanceSnapshot(answered_count=5, recent_correctness=(True, True, True, True, False))
    assert strat.next_difficulty(Difficulty.EASY, snap_high) == Difficulty.MEDIUM

    # 1/5 = 20% -> demote
    snap_low = PerformanceSnapshot(answered_count=5, recent_correctness=(False, False, False, False, True))
    assert strat.next_difficulty(Difficulty.MEDIUM, snap_low) == Difficulty.EASY

    # 3/5 = 60% -> maintain
    snap_mid = PerformanceSnapshot(answered_count=5, recent_correctness=(True, True, False, False, True))
    assert strat.next_difficulty(Difficulty.MEDIUM, snap_mid) == Difficulty.MEDIUM


def test_adaptive_question_selector_tie_breaking() -> None:
    selector = AdaptiveQuestionSelector()
    doc_id = uuid4()
    src = QuestionSourceMeta(document_id=doc_id, page_number=1, excerpt="Source excerpt")

    q_easy = QuestionPayload(
        question_id=uuid4(),
        prompt="Easy Q",
        options=("A", "B"),
        correct_index=0,
        difficulty=Difficulty.EASY,
        explanation="Expl",
        topic="General",
        sources=(src,),
        generation_mode="mock",
        provider="mock",
        created_at=datetime.now(UTC),
    )
    q_hard = QuestionPayload(
        question_id=uuid4(),
        prompt="Hard Q",
        options=("A", "B"),
        correct_index=0,
        difficulty=Difficulty.HARD,
        explanation="Expl",
        topic="General",
        sources=(src,),
        generation_mode="mock",
        provider="mock",
        created_at=datetime.now(UTC),
    )

    pool = [q_easy, q_hard]
    used_ids: set[uuid4] = set()

    # Target is Medium. Distance to Easy (rank 1) is 1. Distance to Hard (rank 3) is 1.
    # Tie breaker rule: break tie toward EASIER (Easy wins)
    chosen = selector.select_next_question(pool, used_ids, Difficulty.MEDIUM)
    assert chosen is not None
    assert chosen.difficulty == Difficulty.EASY
    assert chosen.question_id == q_easy.question_id

    # Pool exhaustion returns None
    used_ids.add(q_easy.question_id)
    used_ids.add(q_hard.question_id)
    assert selector.select_next_question(pool, used_ids, Difficulty.MEDIUM) is None


# ============================================================================
# 3. QUESTION FACTORY & STATE MACHINE TESTS
# ============================================================================


def test_multiple_choice_question_factory() -> None:
    factory = MultipleChoiceQuestionFactory()
    doc_id = uuid4()
    src = QuestionSourceMeta(document_id=doc_id, page_number=1, excerpt="Source citation")

    spec = QuestionSpec(
        question_id=uuid4(),
        document_id=doc_id,
        kind="multiple_choice",
        prompt="What is the factory method pattern?",
        options=("Creation pattern", "Structural pattern", "Behavioral pattern"),
        correct_index=0,
        difficulty=Difficulty.MEDIUM,
        explanation="Defines interface for creating objects.",
        topic="Design Patterns",
        sources=(src,),
    )
    question = factory.create(spec)
    assert question.kind == "multiple_choice"
    assert question.correct_index == 0
    assert len(question.options) == 3

    # Negative test: out-of-bounds correct index
    bad_spec = QuestionSpec(
        question_id=uuid4(),
        document_id=doc_id,
        kind="multiple_choice",
        prompt="Bad prompt",
        options=("Opt 1", "Opt 2"),
        correct_index=5,
        difficulty=Difficulty.EASY,
        explanation="Expl",
        topic="General",
        sources=(src,),
    )
    with pytest.raises(ValidationError):
        factory.create(bad_spec)


def test_exam_state_machine_transitions() -> None:
    created = CreatedState()
    assert created.state_enum == ExamStateEnum.CREATED

    # Cannot submit or complete in Created state
    with pytest.raises(InvalidExamTransitionError):
        created.submit_answer(None, None, datetime.now(UTC))

    with pytest.raises(InvalidExamTransitionError):
        created.complete(None, datetime.now(UTC))

    in_progress = InProgressState()
    # Cannot restart in progress
    with pytest.raises(InvalidExamTransitionError):
        in_progress.start(None, datetime.now(UTC))

    completed = CompletedState()
    # Cannot submit answers when completed
    with pytest.raises(InvalidExamTransitionError):
        completed.submit_answer(None, None, datetime.now(UTC))

    graded = GradedState()
    # Terminal state: cannot execute any transitions
    with pytest.raises(InvalidExamTransitionError):
        graded.start(None, datetime.now(UTC))


# ============================================================================
# 4. DATABASE 11-TABLE PERSISTENCE & UOW TESTS
# ============================================================================


def test_all_11_tables_and_uow_transactions() -> None:
    init_db()
    table_names = list(Base.metadata.tables.keys())
    assert len(table_names) == 11
    expected_tables = {
        "users",
        "documents",
        "document_pages",
        "questions",
        "question_sources",
        "generation_runs",
        "document_permissions",
        "exam_sessions",
        "exam_session_documents",
        "exam_session_questions",
        "exam_answers",
    }
    assert expected_tables.issubset(set(table_names))

    uow = SQLAlchemyUnitOfWork()
    user_id = uuid4()
    doc_id = uuid4()

    with uow:
        assert uow.users is not None
        assert uow.documents is not None

        # 1. users
        unique_email = f"persist_test_{user_id}@example.com"
        user = UserModel(
            id=user_id,
            email_normalized=unique_email,
            password_hash="argon2hash",
            role="student",
        )
        uow.users.add(user)

        # 2. documents
        doc = DocumentModel(
            id=doc_id,
            owner_id=user_id,
            filename="arch.pdf",
            storage_key=f"storage/{doc_id}.pdf",
            sha256="c" * 64,
            size_bytes=4096,
            status=DocumentStatus.READY.value,
            page_count=2,
            extracted_page_count=2,
        )
        uow.documents.add(doc)

    # Verify retrieval in subsequent transaction
    with uow:
        assert uow.users is not None
        assert uow.documents is not None
        fetched_user = uow.users.get_by_id(user_id)
        assert fetched_user is not None
        assert fetched_user.email_normalized == unique_email

        fetched_doc = uow.documents.get_by_id(doc_id)
        assert fetched_doc is not None
        assert fetched_doc.filename == "arch.pdf"


def test_optimistic_concurrency_control() -> None:
    uow = SQLAlchemyUnitOfWork()
    user_id = uuid4()
    doc_id = uuid4()
    sess_id = uuid4()

    with uow:
        assert uow.users is not None
        assert uow.documents is not None
        assert uow.exam_sessions is not None

        uow.users.add(UserModel(id=user_id, email_normalized=f"opt_{user_id}@test.com", password_hash="hash"))
        uow.documents.add(DocumentModel(
            id=doc_id,
            owner_id=user_id,
            filename="test.pdf",
            storage_key=f"key_{doc_id}",
            sha256="d" * 64,
            size_bytes=100,
        ))
        uow.exam_sessions.add(ExamSessionModel(
            id=sess_id,
            student_id=user_id,
            document_id=doc_id,
            version=1,
        ))

    with uow:
        # Optimistic locking: expected version 1 succeeds and becomes 2
        uow.verify_and_increment_version(sess_id, expected_version=1)

    with uow:
        # Version is now 2. Checking against expected 1 must raise ConflictError
        with pytest.raises(ConflictError):
            uow.verify_and_increment_version(sess_id, expected_version=1)


# ============================================================================
# 5. EXAM APPLICATION SERVICE END-TO-END FLOW
# ============================================================================


def test_exam_application_service_flow() -> None:
    init_db()
    uow = SQLAlchemyUnitOfWork()
    student_id = uuid4()
    doc_id = uuid4()
    q1_id = uuid4()
    q2_id = uuid4()

    # Prepopulate document & questions
    with uow:
        assert uow.users is not None
        assert uow.documents is not None
        assert uow.questions is not None

        uow.users.add(UserModel(id=student_id, email_normalized=f"student_{student_id}@test.com", password_hash="pass"))
        uow.documents.add(DocumentModel(
            id=doc_id,
            owner_id=student_id,
            filename="exam_doc.pdf",
            storage_key=f"storage_{doc_id}",
            sha256="e" * 64,
            size_bytes=2048,
        ))

        q1 = QuestionModel(
            id=q1_id,
            document_id=doc_id,
            question_type="multiple_choice",
            prompt="What is clean code?",
            options=["Clear logic", "Messy logic"],
            correct_index=0,
            difficulty="Medium",
            explanation="Code should be readable and intention-revealing.",
            topic="Software Engineering",
            generation_mode="mock",
            provider="offline-mock",
        )
        src1 = QuestionSourceModel(
            id=uuid4(),
            question_id=q1_id,
            document_id=doc_id,
            page_number=1,
            excerpt="Code should be readable and intention-revealing.",
        )
        q1.sources = [src1]
        uow.questions.add(q1)

        q2 = QuestionModel(
            id=q2_id,
            document_id=doc_id,
            question_type="multiple_choice",
            prompt="What is continuous integration?",
            options=["Frequent merges", "Infrequent merges"],
            correct_index=0,
            difficulty="Hard",
            explanation="Developers merge their changes frequently.",
            topic="DevOps",
            generation_mode="mock",
            provider="offline-mock",
        )
        src2 = QuestionSourceModel(
            id=uuid4(),
            question_id=q2_id,
            document_id=doc_id,
            page_number=2,
            excerpt="Developers merge their changes frequently.",
        )
        q2.sources = [src2]
        uow.questions.add(q2)

    app_service = ExamApplicationService(uow=uow)

    # 1. Create Session
    create_req = ExamCreateRequest(
        document_id=doc_id,
        target_question_count=2,
        initial_difficulty=Difficulty.MEDIUM,
        mode=ExamMode.PRACTICE,
    )
    session_out = app_service.create_session(actor_id=student_id, request=create_req)
    assert session_out.state == ExamStateEnum.CREATED
    session_id = session_out.session_id

    # 2. Start Session
    started_out = app_service.start(actor_id=student_id, session_id=session_id)
    assert started_out.state == ExamStateEnum.IN_PROGRESS

    # 3. Request Next Question
    q_view = app_service.next_question(actor_id=student_id, session_id=session_id)
    assert isinstance(q_view, StudentQuestionView)
    assert q_view.sequence_number == 1
    # Verify strict answer key redaction
    assert not hasattr(q_view, "correct_index")
    assert not hasattr(q_view, "explanation")
    assert not hasattr(q_view, "sources")

    # 4. Submit Answer (Idempotent)
    sub_id = uuid4()
    submission = AnswerSubmission(
        submission_id=sub_id,
        session_id=session_id,
        question_id=q_view.question_id,
        selected_index=0,  # Correct
    )
    receipt1 = app_service.submit_answer(actor_id=student_id, submission=submission)
    assert receipt1.is_correct is True

    # Idempotent re-submission returns identical receipt
    receipt2 = app_service.submit_answer(actor_id=student_id, submission=submission)
    assert receipt2.submission_id == receipt1.submission_id
    assert receipt2.is_correct is True

    # 5. Request and Submit Question 2
    q_view2 = app_service.next_question(actor_id=student_id, session_id=session_id)
    assert q_view2.sequence_number == 2
    sub2 = AnswerSubmission(
        submission_id=uuid4(),
        session_id=session_id,
        question_id=q_view2.question_id,
        selected_index=0,
    )
    receipt_final = app_service.submit_answer(actor_id=student_id, submission=sub2)
    assert receipt_final.exam_completed is True

    # 6. Grade Session
    report = app_service.grade(actor_id=student_id, session_id=session_id)
    assert report.state == "Graded"
    assert report.answered_count == 2
    assert report.correct_count == 2
    assert report.score_ratio == 1.0
