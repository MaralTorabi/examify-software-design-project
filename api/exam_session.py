"""Session transitions, adaptive selection, and grading for the prototype."""

from collections import defaultdict
from datetime import UTC, datetime

from core.errors import ConflictError, InvalidExamTransitionError, ValidationError
from core.schemas import AnswerReceipt, ExamResultReport, ExamSessionOut, StudentQuestionView
from core.types import CompletionReason, Difficulty, ExamStateEnum

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
    answers = exam["answers"].values()
    topics = defaultdict(list)
    for answer in answers:
        question = exam["pool"][answer["question_id"]]
        topics[question["topic"]].append((answer["receipt"]["is_correct"], question["sources"]))

    topic_performance = []
    recommendations = []
    review_sources = []
    for topic, entries in topics.items():
        correct_count = sum(correct for correct, _ in entries)
        accuracy = correct_count / len(entries)
        missed_sources = {
            (source["page_number"], source["excerpt"]): source
            for correct, sources in entries
            if not correct
            for source in sources
        }
        sources_by_key = {
            (source["page_number"], source["excerpt"]): source
            for _, sources in entries
            for source in sources
        }
        sources = tuple(sources_by_key.values())
        topic_performance.append(
            {
                "topic": topic,
                "answered_count": len(entries),
                "correct_count": correct_count,
                "accuracy": accuracy,
                "insufficient_evidence": len(entries) < 3,
                "sources": sources,
            }
        )
        review_sources.extend({"topic": topic, **item} for item in missed_sources.values())
        if len(entries) >= 3 and accuracy < 0.60:
            recommendations.append(
                {
                    "topic": topic,
                    "reason": "Accuracy was below 60% on at least three answers.",
                    "suggested_difficulty": Difficulty.EASY
                    if accuracy < 0.40
                    else Difficulty.MEDIUM,
                    "recommended_question_count": 5,
                    "sources": tuple(missed_sources.values()),
                }
            )

    correct_count = sum(answer["receipt"]["is_correct"] for answer in answers)
    report = ExamResultReport(
        session_id=exam["session_id"],
        student_id=exam["student_id"],
        completion_reason=exam["completion_reason"],
        target_question_count=exam["target_question_count"],
        answered_count=len(answers),
        correct_count=correct_count,
        score_ratio=correct_count / len(answers) if answers else None,
        final_difficulty=exam["current_difficulty"],
        topic_performance=tuple(topic_performance),
        weak_topics=tuple(item["topic"] for item in recommendations),
        recommendations=tuple(recommendations),
        generated_at=datetime.now(UTC),
    )
    return {**report.model_dump(mode="json"), "review_sources": review_sources}
