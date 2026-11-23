"""Build validated reports from a completed prototype session."""

from collections import defaultdict
from datetime import UTC, datetime

from core.schemas import ExamResultReport
from core.types import Difficulty


class AnalyticsService:
    """Calculate topic metrics without changing the session."""

    @staticmethod
    def build_report(exam) -> ExamResultReport:
        answers = exam["answers"].values()
        topics = defaultdict(list)
        for answer in answers:
            question = exam["pool"][answer["question_id"]]
            topics[question["topic"]].append((answer["receipt"]["is_correct"], question["sources"]))

        topic_performance = []
        recommendations = []
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
        return report
