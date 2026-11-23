from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from api.auth import CurrentUser
from api.exam_session import (
    accept_answer,
    build_report,
    complete_exam,
    question_view,
    require_state,
    select_question,
    session_view,
)
from api.routes.documents import visible_document
from api.storage import read_exam, save_exam
from core.errors import ConflictError, NotFoundError, ValidationError
from core.schemas import (
    AnswerReceipt,
    AnswerSubmission,
    ExamCreateRequest,
    ExamSessionOut,
    StudentQuestionView,
)
from core.types import CompletionReason, ExamStateEnum, ReviewStatus

router = APIRouter(prefix="/api/v1/exams", tags=["exams"])


class SubmitAnswer(BaseModel):
    submission_id: UUID
    question_id: UUID
    selected_index: Annotated[int, Field(strict=True, ge=0)]
    session_id: UUID | None = None
    schema_version: str = "1.0"


def owned_exam(connection, session_id, user):
    exam = read_exam(connection, session_id)
    if exam is None or exam["student_id"] != str(user.id):
        raise NotFoundError("Exam session not found.")
    return exam


@router.post("", status_code=201)
def create(body: ExamCreateRequest, request: Request, user: CurrentUser) -> ExamSessionOut:
    if body.target_question_count > 30:
        raise ValidationError("The prototype supports up to 30 questions per exam.")
    actor_id = str(user.id)
    exam = {
        "session_id": str(uuid4()),
        "student_id": actor_id,
        "document_id": str(body.document_id),
        "state": ExamStateEnum.CREATED,
        "mode": body.mode,
        "target_question_count": body.target_question_count,
        "current_question_sequence": 0,
        "current_difficulty": body.initial_difficulty,
        "created_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
        "issued_question_id": None,
        "pool": {},
        "answers": {},
    }
    with request.app.state.store.transaction(write=True) as connection:
        visible_document(connection, body.document_id, actor_id)
        save_exam(connection, exam)
    return session_view(exam)


@router.post("/{session_id}/start")
def start(session_id: UUID, request: Request, user: CurrentUser) -> ExamSessionOut:
    with request.app.state.store.transaction(write=True) as connection:
        exam = owned_exam(connection, session_id, user)
        require_state(exam, ExamStateEnum.CREATED)
        document = visible_document(connection, exam["document_id"], str(user.id))
        exam["pool"] = {
            item["question_id"]: item
            for item in document["questions"]
            if item["review_status"] == ReviewStatus.APPROVED
        }
        if not exam["pool"]:
            raise ConflictError("Approve at least one question before starting the exam.")
        exam["state"] = ExamStateEnum.IN_PROGRESS
        save_exam(connection, exam)
    return session_view(exam)


@router.get("/{session_id}/next-question")
def next_question(
    session_id: UUID, request: Request, response: Response, user: CurrentUser
) -> StudentQuestionView | None:
    response.headers["Cache-Control"] = "no-store"
    with request.app.state.store.transaction(write=True) as connection:
        exam = owned_exam(connection, session_id, user)
        question = select_question(exam)
        save_exam(connection, exam)
    return question_view(exam, question)


@router.post("/{session_id}/submit-answer", response_model_exclude_none=True)
def submit_answer(
    session_id: UUID, body: SubmitAnswer, request: Request, user: CurrentUser
) -> AnswerReceipt:
    if body.session_id is not None and body.session_id != session_id:
        raise ValidationError("The session ID does not match the URL.")
    if body.schema_version != "1.0":
        raise ValidationError("Unsupported answer schema version.")
    answer = AnswerSubmission(
        submission_id=body.submission_id,
        session_id=session_id,
        question_id=body.question_id,
        selected_index=body.selected_index,
    )
    with request.app.state.store.transaction(write=True) as connection:
        exam = owned_exam(connection, session_id, user)
        receipt = accept_answer(exam, answer)
        save_exam(connection, exam)
    return receipt


@router.post("/{session_id}/complete")
def complete(session_id: UUID, request: Request, user: CurrentUser) -> ExamSessionOut:
    with request.app.state.store.transaction(write=True) as connection:
        exam = owned_exam(connection, session_id, user)
        if exam["state"] != ExamStateEnum.COMPLETED:
            require_state(exam, ExamStateEnum.IN_PROGRESS)
            complete_exam(exam, CompletionReason.USER_FINISHED)
            save_exam(connection, exam)
    return session_view(exam)


@router.post("/{session_id}/grade")
def grade(session_id: UUID, request: Request, user: CurrentUser):
    with request.app.state.store.transaction(write=True) as connection:
        exam = owned_exam(connection, session_id, user)
        if exam["state"] != ExamStateEnum.GRADED:
            require_state(exam, ExamStateEnum.COMPLETED)
            exam["result"] = build_report(exam)
            exam["state"] = ExamStateEnum.GRADED
            save_exam(connection, exam)
        return exam["result"]


@router.get("/{session_id}/report")
def report(session_id: UUID, request: Request, user: CurrentUser):
    with request.app.state.store.transaction() as connection:
        exam = owned_exam(connection, session_id, user)
        require_state(exam, ExamStateEnum.GRADED)
        return exam["result"]
