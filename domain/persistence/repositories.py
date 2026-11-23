from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from domain.persistence.models import (
    DocumentModel,
    ExamAnswerModel,
    ExamSessionModel,
    QuestionModel,
    UserModel,
)


class UserRepository:
    """Repository handling persistence operations for users."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, user: UserModel) -> UserModel:
        self.session.add(user)
        return user

    def get_by_id(self, user_id: UUID) -> UserModel | None:
        stmt = select(UserModel).where(UserModel.id == user_id)
        return self.session.scalars(stmt).first()

    def get_by_email(self, email: str) -> UserModel | None:
        stmt = select(UserModel).where(UserModel.email_normalized == email.strip().casefold())
        return self.session.scalars(stmt).first()


class DocumentRepository:
    """Repository handling persistence operations for ingested documents."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, document: DocumentModel) -> DocumentModel:
        self.session.add(document)
        return document

    def get_by_id(self, document_id: UUID) -> DocumentModel | None:
        stmt = (
            select(DocumentModel)
            .options(joinedload(DocumentModel.pages))
            .where(DocumentModel.id == document_id)
        )
        return self.session.scalars(stmt).unique().first()

    def list_by_owner(self, owner_id: UUID) -> list[DocumentModel]:
        stmt = (
            select(DocumentModel)
            .where(DocumentModel.owner_id == owner_id, DocumentModel.deleted_at.is_(None))
            .order_by(DocumentModel.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())


class QuestionRepository:
    """Repository handling persistence operations for question bank."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, question: QuestionModel) -> QuestionModel:
        self.session.add(question)
        return question

    def add_all(self, questions: list[QuestionModel]) -> None:
        self.session.add_all(questions)

    def get_by_id(self, question_id: UUID) -> QuestionModel | None:
        stmt = (
            select(QuestionModel)
            .options(joinedload(QuestionModel.sources))
            .where(QuestionModel.id == question_id)
        )
        return self.session.scalars(stmt).unique().first()

    def list_by_document(self, document_id: UUID) -> list[QuestionModel]:
        stmt = (
            select(QuestionModel)
            .options(joinedload(QuestionModel.sources))
            .where(QuestionModel.document_id == document_id)
            .order_by(QuestionModel.created_at.asc())
        )
        return list(self.session.scalars(stmt).unique().all())


class ExamSessionRepository:
    """Repository handling persistence operations for student exam sessions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, exam_session: ExamSessionModel) -> ExamSessionModel:
        self.session.add(exam_session)
        return exam_session

    def get_by_id(self, session_id: UUID) -> ExamSessionModel | None:
        stmt = (
            select(ExamSessionModel)
            .options(
                joinedload(ExamSessionModel.answers),
                joinedload(ExamSessionModel.session_questions),
            )
            .where(ExamSessionModel.id == session_id)
        )
        return self.session.scalars(stmt).unique().first()

    def list_by_student(self, student_id: UUID) -> list[ExamSessionModel]:
        stmt = (
            select(ExamSessionModel)
            .where(ExamSessionModel.student_id == student_id)
            .order_by(ExamSessionModel.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())


class ExamAnswerRepository:
    """Repository handling persistence operations for student answers."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, answer: ExamAnswerModel) -> ExamAnswerModel:
        self.session.add(answer)
        return answer

    def get_by_submission_id(self, submission_id: UUID) -> ExamAnswerModel | None:
        stmt = select(ExamAnswerModel).where(ExamAnswerModel.submission_id == submission_id)
        return self.session.scalars(stmt).first()

    def list_by_session(self, session_id: UUID) -> list[ExamAnswerModel]:
        stmt = (
            select(ExamAnswerModel)
            .where(ExamAnswerModel.session_id == session_id)
            .order_by(ExamAnswerModel.submitted_at.asc())
        )
        return list(self.session.scalars(stmt).all())
