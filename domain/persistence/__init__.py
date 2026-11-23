"""Persistence package: database setup, 11 ORM models, repositories, and Unit of Work."""

from domain.persistence.database import (
    get_db_session,
    get_engine,
    get_session_factory,
    init_db,
)
from domain.persistence.models import (
    Base,
    DocumentModel,
    DocumentPageModel,
    DocumentPermissionModel,
    ExamAnswerModel,
    ExamSessionDocumentModel,
    ExamSessionModel,
    ExamSessionQuestionModel,
    GenerationRunModel,
    QuestionModel,
    QuestionSourceModel,
    UserModel,
)
from domain.persistence.repositories import (
    DocumentRepository,
    ExamAnswerRepository,
    ExamSessionRepository,
    QuestionRepository,
    UserRepository,
)
from domain.persistence.uow import SQLAlchemyUnitOfWork

__all__ = [
    "Base",
    "get_engine",
    "get_session_factory",
    "get_db_session",
    "init_db",
    "UserModel",
    "DocumentModel",
    "DocumentPageModel",
    "QuestionModel",
    "QuestionSourceModel",
    "GenerationRunModel",
    "DocumentPermissionModel",
    "ExamSessionModel",
    "ExamSessionDocumentModel",
    "ExamSessionQuestionModel",
    "ExamAnswerModel",
    "UserRepository",
    "DocumentRepository",
    "QuestionRepository",
    "ExamSessionRepository",
    "ExamAnswerRepository",
    "SQLAlchemyUnitOfWork",
]
