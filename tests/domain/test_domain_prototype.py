from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from core.errors import ConflictError, InvalidExamTransitionError
from core.schemas import (
    AnswerSubmission,
    ExamCreateRequest,
    QuestionSourceMeta,
    StudentQuestionView,
)
from core.types import Difficulty, ExamMode, ExamStateEnum
from domain.application.exam_service import ExamApplicationService
from domain.patterns.exam_states import (
    CompletedState,
    CreatedState,
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


def test_question_factory() -> None:
    factory = MultipleChoiceQuestionFactory()
    doc_id = uuid4()
    src = QuestionSourceMeta(document_id=doc_id, page_number=1, excerpt="Source citation")

    spec = QuestionSpec(
        question_id=uuid4(),
        document_id=doc_id,
        kind="multiple_choice",
        prompt="What is domain-driven design?",
        options=("Modeling software to match a domain", "Database-first approach"),
        correct_index=0,
        difficulty=Difficulty.MEDIUM,
        explanation="DDD focuses on core domain logic.",
        topic="Software Design",
        sources=(src,),
    )
    question = factory.create(spec)
    assert question.kind == "multiple_choice"
    assert question.correct_index == 0


def test_exam_states_pattern() -> None:
    created = CreatedState()
    with pytest.raises(InvalidExamTransitionError):
        created.submit_answer(None, None, datetime.now(UTC))

    in_progress = InProgressState()
    with pytest.raises(InvalidExamTransitionError):
        in_progress.start(None, datetime.now(UTC))

    completed = CompletedState()
    with pytest.raises(InvalidExamTransitionError):
        completed.submit_answer(None, None, datetime.now(UTC))


def test_persistence_tables_count() -> None:
    init_db()
    assert len(Base.metadata.tables) == 11


def test_uow_optimistic_locking() -> None:
    uow = SQLAlchemyUnitOfWork()
    user_id = uuid4()
    doc_id = uuid4()
    sess_id = uuid4()

    with uow:
        assert uow.users is not None
        assert uow.documents is not None
        assert uow.exam_sessions is not None

        uow.users.add(UserModel(id=user_id, email_normalized=f"lock_{user_id}@test.com", password_hash="hash"))
        uow.documents.add(DocumentModel(
            id=doc_id,
            owner_id=user_id,
            filename="doc.pdf",
            storage_key=f"storage_{doc_id}",
            sha256="f" * 64,
            size_bytes=100,
        ))
        uow.exam_sessions.add(ExamSessionModel(
            id=sess_id,
            student_id=user_id,
            document_id=doc_id,
            version=1,
        ))

    with uow:
        uow.verify_and_increment_version(sess_id, expected_version=1)

    with uow:
        with pytest.raises(ConflictError):
            uow.verify_and_increment_version(sess_id, expected_version=1)


def test_application_service_full_cycle() -> None:
    init_db()
    uow = SQLAlchemyUnitOfWork()
    student_id = uuid4()
    doc_id = uuid4()
    q_id = uuid4()

    with uow:
        assert uow.users is not None
        assert uow.documents is not None
        assert uow.questions is not None

        uow.users.add(UserModel(id=student_id, email_normalized=f"cycle_{student_id}@test.com", password_hash="pass"))
        uow.documents.add(DocumentModel(
            id=doc_id,
            owner_id=student_id,
            filename="test.pdf",
            storage_key=f"key_{doc_id}",
            sha256="1" * 64,
            size_bytes=500,
        ))
        q = QuestionModel(
            id=q_id,
            document_id=doc_id,
            question_type="multiple_choice",
            prompt="Is testing crucial?",
            options=["Yes", "No"],
            correct_index=0,
            difficulty="Easy",
            explanation="Testing ensures system correctness.",
            topic="Quality Assurance",
            generation_mode="mock",
            provider="mock",
        )
        src = QuestionSourceModel(
            id=uuid4(),
            question_id=q_id,
            document_id=doc_id,
            page_number=1,
            excerpt="Testing ensures system correctness.",
        )
        q.sources = [src]
        uow.questions.add(q)

    service = ExamApplicationService(uow=uow)
    create_req = ExamCreateRequest(
        document_id=doc_id,
        target_question_count=1,
        initial_difficulty=Difficulty.EASY,
        mode=ExamMode.PRACTICE,
    )
    s_out = service.create_session(actor_id=student_id, request=create_req)
    assert s_out.state == ExamStateEnum.CREATED

    service.start(actor_id=student_id, session_id=s_out.session_id)
    view = service.next_question(actor_id=student_id, session_id=s_out.session_id)
    assert isinstance(view, StudentQuestionView)

    receipt = service.submit_answer(
        actor_id=student_id,
        submission=AnswerSubmission(
            submission_id=uuid4(),
            session_id=s_out.session_id,
            question_id=view.question_id,
            selected_index=0,
        ),
    )
    assert receipt.is_correct is True
    assert receipt.exam_completed is True

    report = service.grade(actor_id=student_id, session_id=s_out.session_id)
    assert report.state == "Graded"
    assert report.correct_count == 1
