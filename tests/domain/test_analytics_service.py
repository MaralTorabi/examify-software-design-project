from uuid import uuid4

from core.schemas import ExamResultReport
from domain.analytics.analytics_service import AnalyticsService


def test_empty_completed_exam_returns_validated_report():
    report = AnalyticsService.build_report({
        "session_id": str(uuid4()), "student_id": str(uuid4()),
        "completion_reason": "user_finished", "target_question_count": 5,
        "current_difficulty": "Medium", "answers": {}, "pool": {},
    })
    assert isinstance(report, ExamResultReport)
    assert report.answered_count == 0
    assert report.score_ratio is None
