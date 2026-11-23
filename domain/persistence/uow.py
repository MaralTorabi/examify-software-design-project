from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from core.errors import ConflictError
from domain.persistence.database import get_session_factory
from domain.persistence.models import ExamSessionModel
from domain.persistence.repositories import (
    DocumentRepository,
    ExamAnswerRepository,
    ExamSessionRepository,
    QuestionRepository,
    UserRepository,
)


class SQLAlchemyUnitOfWork:
    """Unit of Work pattern managing database transactions and repository lifecycles with optimistic locking."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self.session_factory = session_factory or get_session_factory()
        self.session: Session | None = None

        self.users: UserRepository | None = None
        self.documents: DocumentRepository | None = None
        self.questions: QuestionRepository | None = None
        self.exam_sessions: ExamSessionRepository | None = None
        self.exam_answers: ExamAnswerRepository | None = None

    def __enter__(self) -> SQLAlchemyUnitOfWork:
        self.session = self.session_factory()
        self.users = UserRepository(self.session)
        self.documents = DocumentRepository(self.session)
        self.questions = QuestionRepository(self.session)
        self.exam_sessions = ExamSessionRepository(self.session)
        self.exam_answers = ExamAnswerRepository(self.session)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.session is not None:
            if exc_type is not None:
                self.session.rollback()
            else:
                try:
                    self.session.commit()
                except Exception:
                    self.session.rollback()
                    raise
            self.session.close()

    def commit(self) -> None:
        if self.session:
            self.session.commit()

    def rollback(self) -> None:
        if self.session:
            self.session.rollback()

    def verify_and_increment_version(
        self,
        session_id: UUID,
        expected_version: int,
    ) -> ExamSessionModel:
        """Enforces optimistic concurrency control on an exam session.

        Raises ConflictError if the record's version does not match expected_version.
        Increments the version upon match.
        """
        assert self.exam_sessions is not None
        exam_session = self.exam_sessions.get_by_id(session_id)
        if not exam_session:
            raise ConflictError(f"Exam session {session_id} not found.")

        if exam_session.version != expected_version:
            raise ConflictError(
                f"Optimistic lock conflict on session {session_id}: "
                f"expected version {expected_version}, found {exam_session.version}."
            )

        exam_session.version += 1
        return exam_session
