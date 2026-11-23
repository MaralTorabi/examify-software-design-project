from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative class for all Examify persistence entities."""
    pass


# 1. users (ILF 1)
class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email_normalized: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="student")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    documents: Mapped[list[DocumentModel]] = relationship("DocumentModel", back_populates="owner")
    sessions: Mapped[list[ExamSessionModel]] = relationship("ExamSessionModel", back_populates="student")


# 2. documents (ILF 2)
class DocumentModel(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Uploaded")
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    processing_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped[UserModel] = relationship("UserModel", back_populates="documents")
    pages: Mapped[list[DocumentPageModel]] = relationship("DocumentPageModel", back_populates="document", cascade="all, delete-orphan")
    questions: Mapped[list[QuestionModel]] = relationship("QuestionModel", back_populates="document")


# 3. document_pages (ILF 3)
class DocumentPageModel(Base):
    __tablename__ = "document_pages"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    document: Mapped[DocumentModel] = relationship("DocumentModel", back_populates="pages")


# 4. questions (ILF 4)
class QuestionModel(Base):
    __tablename__ = "questions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    question_type: Mapped[str] = mapped_column(String(30), default="multiple_choice", nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    correct_index: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    generation_mode: Mapped[str] = mapped_column(String(20), default="mock", nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="offline-mock", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    document: Mapped[DocumentModel] = relationship("DocumentModel", back_populates="questions")
    sources: Mapped[list[QuestionSourceModel]] = relationship("QuestionSourceModel", back_populates="question", cascade="all, delete-orphan")


# 5. question_sources (ILF 5)
class QuestionSourceModel(Base):
    __tablename__ = "question_sources"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    question_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    question: Mapped[QuestionModel] = relationship("QuestionModel", back_populates="sources")


# 6. generation_runs (ILF 6)
class GenerationRunModel(Base):
    __tablename__ = "generation_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_count: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_count: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)


# 7. document_permissions (ILF 7)
class DocumentPermissionModel(Base):
    __tablename__ = "document_permissions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_level: Mapped[str] = mapped_column(String(20), default="read", nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)


# 8. exam_sessions (ILF 8)
class ExamSessionModel(Base):
    __tablename__ = "exam_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    student_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="Created", nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="practice", nullable=False)
    target_question_count: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    current_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_difficulty: Mapped[str] = mapped_column(String(10), default="Medium", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    student: Mapped[UserModel] = relationship("UserModel", back_populates="sessions")
    answers: Mapped[list[ExamAnswerModel]] = relationship("ExamAnswerModel", back_populates="session", cascade="all, delete-orphan")
    session_questions: Mapped[list[ExamSessionQuestionModel]] = relationship("ExamSessionQuestionModel", back_populates="session", cascade="all, delete-orphan")


# 9. exam_session_documents (ILF 9)
class ExamSessionDocumentModel(Base):
    __tablename__ = "exam_session_documents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False)
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)


# 10. exam_session_questions (ILF 10)
class ExamSessionQuestionModel(Base):
    __tablename__ = "exam_session_questions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="issued", nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    session: Mapped[ExamSessionModel] = relationship("ExamSessionModel", back_populates="session_questions")


# 11. exam_answers (ILF 11)
class ExamAnswerModel(Base):
    __tablename__ = "exam_answers"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    submission_id: Mapped[UUID] = mapped_column(Uuid, unique=True, nullable=False, index=True)
    session_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False)
    selected_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    session: Mapped[ExamSessionModel] = relationship("ExamSessionModel", back_populates="answers")
