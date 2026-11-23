"""Session transitions, adaptive selection, and grading for the prototype."""

from datetime import UTC, datetime

from core.errors import ConflictError, InvalidExamTransitionError, ValidationError
from core.schemas import AnswerReceipt, ExamSessionOut, StudentQuestionView
from core.types import CompletionReason, Difficulty, ExamStateEnum
from domain.analytics.analytics_service import AnalyticsService

LEVELS = (Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD)


def require_state(exam, state):
    if exam["state"] != state:
        raise InvalidExamTransitionError(f"This action requires an exam in state {state}.")


def session_view(exam):
    return ExamSessionOut.model_validate({key: exam[key] for key in ExamSessionOut.model_fields})


def complete_exam(exam, reason):
    exam["state"] = ExamStateEnum.COMPLETED
    exam["completed_at"] = datetime.now(UTC).isoformat()
    exam["completion_reason"] = reason
    exam["issued_question_id"] = None


def select_question(exam):
    require_state(exam, ExamStateEnum.IN_PROGRESS)
    pending_id = exam["issued_question_id"]
    if pending_id:
        return exam["pool"][pending_id]
    answered = {entry["question_id"] for entry in exam["answers"].values()}
    available = [item for key, item in exam["pool"].items() if key not in answered]
    if not available:
        complete_exam(exam, CompletionReason.POOL_EXHAUSTED)
        return None
    target = LEVELS.index(exam["current_difficulty"])

    def rank(item):
        level = LEVELS.index(item["difficulty"])
        return abs(level - target), level

    chosen = min(available, key=rank)
    exam["issued_question_id"] = chosen["question_id"]
    exam["current_question_sequence"] += 1
    return chosen


def question_view(exam, question):
    if question is None:
        return None
    return StudentQuestionView(
        session_id=exam["session_id"],
        question_id=question["question_id"],
        sequence_number=exam["current_question_sequence"],
        prompt=question["prompt"],
        options=question["options"],
        difficulty=question["difficulty"],
        topic=question["topic"],
    )


def accept_answer(exam, answer):
    submission_id = str(answer.submission_id)
    question_id = str(answer.question_id)
    existing = exam["answers"].get(submission_id)
    if existing:
        if (existing["question_id"], existing["selected_index"]) != (
            question_id,
            answer.selected_index,
        ):
            raise ConflictError("The submission ID is already in use.")
        return AnswerReceipt.model_validate(existing["receipt"])

    require_state(exam, ExamStateEnum.IN_PROGRESS)
    if exam["issued_question_id"] != question_id:
        raise ConflictError("The submitted question is not awaiting an answer.")
    question = exam["pool"][question_id]
    if answer.selected_index >= len(question["options"]):
        raise ValidationError("The selected option does not exist.")
    is_correct = answer.selected_index == question["correct_index"]
    if exam["answers"]:
        previous = next(reversed(exam["answers"].values()))["receipt"]["is_correct"]
        if is_correct == previous:
            level = LEVELS.index(exam["current_difficulty"])
            level += 1 if is_correct else -1
            exam["current_difficulty"] = LEVELS[max(0, min(level, len(LEVELS) - 1))]

    exam["issued_question_id"] = None
    answered_count = len(exam["answers"]) + 1
    if answered_count == exam["target_question_count"]:
        complete_exam(exam, CompletionReason.TARGET_REACHED)
    elif answered_count == len(exam["pool"]):
        complete_exam(exam, CompletionReason.POOL_EXHAUSTED)
    receipt = AnswerReceipt(
        submission_id=submission_id,
        session_id=exam["session_id"],
        question_id=question_id,
        is_correct=is_correct,
        next_difficulty=exam["current_difficulty"],
        exam_completed=exam["state"] == ExamStateEnum.COMPLETED,
    )
    exam["answers"][submission_id] = {
        "question_id": question_id,
        "selected_index": answer.selected_index,
        "receipt": receipt.model_dump(mode="json", exclude_none=True),
    }
    return receipt


def build_report(exam):
    report = AnalyticsService.build_report(exam)
    review_sources = {}
    for answer in exam["answers"].values():
        if answer["receipt"]["is_correct"]:
            continue
        question = exam["pool"][answer["question_id"]]
        for source in question["sources"]:
            key = (question["topic"], source["document_id"], source["page_number"], source["excerpt"])
            review_sources[key] = {"topic": question["topic"], **source}
    return {**report.model_dump(mode="json"), "review_sources": list(review_sources.values())}
