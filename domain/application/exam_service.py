from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from core.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from core.schemas import (
    AnswerReceipt,
    AnswerSubmission,
    ExamCreateRequest,
    ExamResultReport,
    ExamSessionOut,
    PracticeRecommendation,
    QuestionPayload,
    QuestionSourceMeta,
    StudentQuestionView,
    TopicPerformance,
)
from core.types import (
    CompletionReason,
    Difficulty,
    ExamMode,
    ExamStateEnum,
)
from domain.patterns.exam_states import state_from_enum
from domain.persistence.models import (
    ExamAnswerModel,
    ExamSessionDocumentModel,
    ExamSessionModel,
    ExamSessionQuestionModel,
    QuestionModel,
)
from domain.persistence.uow import SQLAlchemyUnitOfWork
from services.adaptive.engine import AdaptiveQuestionSelector


def _to_aware(dt: datetime | None) -> datetime | None:
    """Ensures datetime read from SQLite has UTC timezone info for Pydantic AwareDatetime."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class ExamApplicationService:
    """Orchestrates adaptive exam session lifecycle, question issuance, answer verification, and grading."""

    def __init__(
        self,
        uow: SQLAlchemyUnitOfWork | None = None,
        selector: AdaptiveQuestionSelector | None = None,
    ) -> None:
        self.uow = uow or SQLAlchemyUnitOfWork()
        self.selector = selector or AdaptiveQuestionSelector()

    def _model_to_payload(self, q_model: QuestionModel) -> QuestionPayload:
        sources = tuple(
            QuestionSourceMeta(
                document_id=s.document_id,
                page_number=s.page_number,
                excerpt=s.excerpt,
            )
            for s in q_model.sources
        )
        return QuestionPayload(
            question_id=q_model.id,
            prompt=q_model.prompt,
            options=tuple(q_model.options),
            correct_index=q_model.correct_index,
            difficulty=Difficulty(q_model.difficulty),
            explanation=q_model.explanation,
            topic=q_model.topic,
            sources=sources,
            generation_mode="mock" if q_model.generation_mode == "mock" else "live",
            provider=q_model.provider,
            created_at=_to_aware(q_model.created_at),  # type: ignore[arg-type]
        )

    def create_session(
        self,
        actor_id: UUID,
        request: ExamCreateRequest,
    ) -> ExamSessionOut:
        """Creates a new exam session in Created state."""
        with self.uow:
            assert self.uow.documents is not None
            assert self.uow.exam_sessions is not None

            doc = self.uow.documents.get_by_id(request.document_id)
            if not doc:
                raise NotFoundError(f"Document {request.document_id} does not exist.")

            session_id = uuid4()
            now = datetime.now(UTC)

            session_model = ExamSessionModel(
                id=session_id,
                student_id=actor_id,
                document_id=request.document_id,
                state=ExamStateEnum.CREATED.value,
                mode=request.mode.value,
                target_question_count=request.target_question_count,
                current_sequence=0,
                current_difficulty=request.initial_difficulty.value,
                version=1,
                created_at=now,
                updated_at=now,
            )
            self.uow.exam_sessions.add(session_model)
            assert self.uow.session is not None
            self.uow.session.flush()

            session_doc = ExamSessionDocumentModel(
                id=uuid4(),
                session_id=session_id,
                document_id=request.document_id,
                attached_at=now,
            )
            self.uow.session.add(session_doc)

            return ExamSessionOut(
                session_id=session_model.id,
                student_id=session_model.student_id,
                document_id=session_model.document_id,
                state=ExamStateEnum.CREATED,
                mode=request.mode,
                target_question_count=session_model.target_question_count,
                current_question_sequence=0,
                current_difficulty=request.initial_difficulty,
                created_at=_to_aware(session_model.created_at),  # type: ignore[arg-type]
            )

    def start(self, actor_id: UUID, session_id: UUID) -> ExamSessionOut:
        """Starts an exam session, transitioning state from Created to InProgress."""
        with self.uow:
            assert self.uow.exam_sessions is not None
            session_model = self.uow.exam_sessions.get_by_id(session_id)
            if not session_model:
                raise NotFoundError(f"Exam session {session_id} not found.")

            if session_model.student_id != actor_id:
                raise AuthorizationError("Actor is not authorized for this exam session.")

            current_state = state_from_enum(ExamStateEnum(session_model.state))
            now = datetime.now(UTC)

            # Context adapter to apply state transition
            class StateContext:
                def __init__(self, s_model: ExamSessionModel) -> None:
                    self.s_model = s_model

                def transition_to(self, new_state: Any) -> None:
                    self.s_model.state = new_state.state_enum.value
                    self.s_model.updated_at = datetime.now(UTC)

            current_state.start(StateContext(session_model), now)
            session_model.version += 1

            return ExamSessionOut(
                session_id=session_model.id,
                student_id=session_model.student_id,
                document_id=session_model.document_id,
                state=ExamStateEnum(session_model.state),
                mode=ExamMode(session_model.mode),
                target_question_count=session_model.target_question_count,
                current_question_sequence=session_model.current_sequence,
                current_difficulty=Difficulty(session_model.current_difficulty),
                created_at=_to_aware(session_model.created_at),  # type: ignore[arg-type]
            )

    def next_question(
        self,
        actor_id: UUID,
        session_id: UUID,
    ) -> StudentQuestionView:
        """Selects and issues the next adaptive question, strictly redacting answers/sources/explanations."""
        with self.uow:
            assert self.uow.exam_sessions is not None
            assert self.uow.questions is not None
            session_model = self.uow.exam_sessions.get_by_id(session_id)
            if not session_model:
                raise NotFoundError(f"Exam session {session_id} not found.")

            if session_model.student_id != actor_id:
                raise AuthorizationError("Actor is not authorized for this exam session.")

            if session_model.state != ExamStateEnum.IN_PROGRESS.value:
                raise ValidationError(
                    f"Cannot issue question: exam session is in '{session_model.state}' state.",
                    code="EXAM_NOT_IN_PROGRESS",
                )

            # Check if current question sequence reached target
            if session_model.current_sequence >= session_model.target_question_count:
                raise ValidationError(
                    "Exam session target question count has already been reached.",
                    code="TARGET_REACHED",
                )

            # Fetch question pool for the document
            q_models = self.uow.questions.list_by_document(session_model.document_id)
            if not q_models:
                raise NotFoundError(
                    f"No questions found for document {session_model.document_id}."
                )

            pool = [self._model_to_payload(qm) for qm in q_models]

            # Already issued question IDs in this session
            used_ids = {sq.question_id for sq in session_model.session_questions}

            target_difficulty = Difficulty(session_model.current_difficulty)
            selected_question = self.selector.select_next_question(
                pool=pool,
                used_question_ids=used_ids,
                target_difficulty=target_difficulty,
            )

            if not selected_question:
                raise ValidationError(
                    "Question pool exhausted for this exam session.",
                    code="POOL_EXHAUSTED",
                )

            # Increment sequence number
            next_sequence = session_model.current_sequence + 1
            session_model.current_sequence = next_sequence
            session_model.version += 1
            now = datetime.now(UTC)

            # Record session question
            session_q = ExamSessionQuestionModel(
                id=uuid4(),
                session_id=session_id,
                question_id=selected_question.question_id,
                sequence_number=next_sequence,
                status="issued",
                issued_at=now,
            )
            assert self.uow.session is not None
            self.uow.session.add(session_q)

            # Return strictly redacted view
            return StudentQuestionView.from_payload(
                payload=selected_question,
                sequence_number=next_sequence,
                session_id=session_id,
            )

    def submit_answer(
        self,
        actor_id: UUID,
        submission: AnswerSubmission,
    ) -> AnswerReceipt:
        """Processes a student's answer submission idempotently and calculates adaptive progression."""
        with self.uow:
            assert self.uow.exam_sessions is not None
            assert self.uow.exam_answers is not None
            assert self.uow.questions is not None

            session_model = self.uow.exam_sessions.get_by_id(submission.session_id)
            if not session_model:
                raise NotFoundError(f"Exam session {submission.session_id} not found.")

            if session_model.student_id != actor_id:
                raise AuthorizationError("Actor is not authorized for this exam session.")

            # Idempotency check: if this submission_id was already recorded, return existing receipt
            existing = self.uow.exam_answers.get_by_submission_id(submission.submission_id)
            if existing:
                q_model = self.uow.questions.get_by_id(existing.question_id)
                assert q_model is not None
                is_practice = session_model.mode == ExamMode.PRACTICE.value
                return AnswerReceipt(
                    submission_id=existing.submission_id,
                    session_id=existing.session_id,
                    question_id=existing.question_id,
                    is_correct=existing.is_correct,
                    correct_index=q_model.correct_index if is_practice else None,
                    explanation=q_model.explanation if is_practice else None,
                    next_difficulty=Difficulty(session_model.current_difficulty),
                    exam_completed=session_model.state in (ExamStateEnum.COMPLETED.value, ExamStateEnum.GRADED.value),
                )

            # State check
            if session_model.state != ExamStateEnum.IN_PROGRESS.value:
                raise ValidationError(
                    f"Cannot submit answer: session is in '{session_model.state}' state.",
                    code="EXAM_NOT_IN_PROGRESS",
                )

            # Fetch question to grade answer
            q_model = self.uow.questions.get_by_id(submission.question_id)
            if not q_model:
                raise NotFoundError(f"Question {submission.question_id} not found.")

            if submission.selected_index >= len(q_model.options):
                raise ValidationError(
                    f"Selected index {submission.selected_index} is outside options.",
                    code="INVALID_OPTION_INDEX",
                )

            is_correct = submission.selected_index == q_model.correct_index
            now = datetime.now(UTC)

            # Persist answer
            answer_record = ExamAnswerModel(
                id=uuid4(),
                submission_id=submission.submission_id,
                session_id=submission.session_id,
                question_id=submission.question_id,
                selected_index=submission.selected_index,
                is_correct=is_correct,
                version=1,
                submitted_at=now,
            )
            self.uow.exam_answers.add(answer_record)

            # Calculate adaptive difficulty progression
            prior_answers = self.uow.exam_answers.list_by_session(session_model.id)
            correctness_history = tuple(a.is_correct for a in prior_answers) + (is_correct,)

            next_diff = self.selector.determine_next_difficulty(
                current_difficulty=Difficulty(session_model.current_difficulty),
                recent_correctness=correctness_history,
            )
            session_model.current_difficulty = next_diff.value
            session_model.version += 1

            # Check if all target questions have now been answered
            exam_completed = len(correctness_history) >= session_model.target_question_count
            if exam_completed:
                session_model.state = ExamStateEnum.COMPLETED.value
                session_model.completed_at = now

            is_practice = session_model.mode == ExamMode.PRACTICE.value
            return AnswerReceipt(
                submission_id=submission.submission_id,
                session_id=submission.session_id,
                question_id=submission.question_id,
                is_correct=is_correct,
                correct_index=q_model.correct_index if is_practice else None,
                explanation=q_model.explanation if is_practice else None,
                next_difficulty=next_diff,
                exam_completed=exam_completed,
            )

    def complete(
        self,
        actor_id: UUID,
        session_id: UUID,
        reason: CompletionReason = CompletionReason.USER_FINISHED,
    ) -> ExamSessionOut:
        """Completes an active exam session."""
        with self.uow:
            assert self.uow.exam_sessions is not None
            session_model = self.uow.exam_sessions.get_by_id(session_id)
            if not session_model:
                raise NotFoundError(f"Exam session {session_id} not found.")

            if session_model.student_id != actor_id:
                raise AuthorizationError("Actor is not authorized for this exam session.")

            current_state = state_from_enum(ExamStateEnum(session_model.state))
            now = datetime.now(UTC)

            class CompleteContext:
                def __init__(self, s_model: ExamSessionModel) -> None:
                    self.s_model = s_model
                    self.completed_at: datetime | None = None

                def transition_to(self, new_state: Any) -> None:
                    self.s_model.state = new_state.state_enum.value
                    self.s_model.updated_at = datetime.now(UTC)

            ctx = CompleteContext(session_model)
            current_state.complete(ctx, now)
            session_model.completed_at = ctx.completed_at or now
            session_model.version += 1

            return ExamSessionOut(
                session_id=session_model.id,
                student_id=session_model.student_id,
                document_id=session_model.document_id,
                state=ExamStateEnum(session_model.state),
                mode=ExamMode(session_model.mode),
                target_question_count=session_model.target_question_count,
                current_question_sequence=session_model.current_sequence,
                current_difficulty=Difficulty(session_model.current_difficulty),
                created_at=_to_aware(session_model.created_at),  # type: ignore[arg-type]
                completed_at=_to_aware(session_model.completed_at),
            )

    def grade(
        self,
        actor_id: UUID,
        session_id: UUID,
    ) -> ExamResultReport:
        """Grades a completed exam session, calculating topic-level metrics and remedial recommendations."""
        with self.uow:
            assert self.uow.exam_sessions is not None
            assert self.uow.exam_answers is not None
            assert self.uow.questions is not None

            session_model = self.uow.exam_sessions.get_by_id(session_id)
            if not session_model:
                raise NotFoundError(f"Exam session {session_id} not found.")

            if session_model.student_id != actor_id:
                raise AuthorizationError("Actor is not authorized for this exam session.")

            current_state = state_from_enum(ExamStateEnum(session_model.state))
            now = datetime.now(UTC)

            # Retrieve answers and questions
            answers = self.uow.exam_answers.list_by_session(session_id)
            answered_count = len(answers)
            correct_count = sum(1 for a in answers if a.is_correct)
            score_ratio = (correct_count / answered_count) if answered_count > 0 else None

            # Group performance by topic
            topic_map: dict[str, dict[str, Any]] = {}
            for a in answers:
                q = self.uow.questions.get_by_id(a.question_id)
                if not q:
                    continue
                if q.topic not in topic_map:
                    topic_map[q.topic] = {
                        "answered": 0,
                        "correct": 0,
                        "sources": [],
                    }
                topic_map[q.topic]["answered"] += 1
                if a.is_correct:
                    topic_map[q.topic]["correct"] += 1

                for s in q.sources:
                    src_meta = QuestionSourceMeta(
                        document_id=s.document_id,
                        page_number=s.page_number,
                        excerpt=s.excerpt,
                    )
                    if src_meta not in topic_map[q.topic]["sources"]:
                        topic_map[q.topic]["sources"].append(src_meta)

            topic_performances: list[TopicPerformance] = []
            weak_topics: list[str] = []
            recommendations: list[PracticeRecommendation] = []

            for topic, stats in topic_map.items():
                t_answered = stats["answered"]
                t_correct = stats["correct"]
                t_acc = t_correct / t_answered
                t_insufficient = t_answered < 3

                # Ensure at least 1 source
                sources_tuple = tuple(stats["sources"])
                if not sources_tuple:
                    sources_tuple = (
                        QuestionSourceMeta(
                            document_id=session_model.document_id,
                            page_number=1,
                            excerpt="Document source reference.",
                        ),
                    )

                tp = TopicPerformance(
                    topic=topic,
                    answered_count=t_answered,
                    correct_count=t_correct,
                    accuracy=t_acc,
                    insufficient_evidence=t_insufficient,
                    sources=sources_tuple,
                )
                topic_performances.append(tp)

                if not t_insufficient and t_acc < 0.60:
                    weak_topics.append(topic)
                    recommendations.append(
                        PracticeRecommendation(
                            topic=topic,
                            reason=f"Accuracy is {t_acc:.0%}, below the 60% competency threshold.",
                            suggested_difficulty=Difficulty.EASY,
                            recommended_question_count=5,
                            sources=sources_tuple,
                        )
                    )

            # Determine completion reason
            if answered_count >= session_model.target_question_count:
                completion_reason = CompletionReason.TARGET_REACHED
            else:
                completion_reason = CompletionReason.USER_FINISHED

            report = ExamResultReport(
                session_id=session_id,
                student_id=actor_id,
                state="Graded",
                completion_reason=completion_reason,
                target_question_count=session_model.target_question_count,
                answered_count=answered_count,
                correct_count=correct_count,
                score_ratio=score_ratio,
                final_difficulty=Difficulty(session_model.current_difficulty),
                topic_performance=tuple(topic_performances),
                weak_topics=tuple(weak_topics),
                recommendations=tuple(recommendations),
                generated_at=now,
            )

            # State transition to Graded
            class GradeContext:
                def __init__(self, s_model: ExamSessionModel) -> None:
                    self.s_model = s_model

                def transition_to(self, new_state: Any) -> None:
                    self.s_model.state = new_state.state_enum.value
                    self.s_model.updated_at = datetime.now(UTC)

            current_state.grade(GradeContext(session_model), report, now)
            session_model.version += 1

            return report
