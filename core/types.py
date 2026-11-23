from __future__ import annotations

from enum import StrEnum
from typing import Literal


class Role(StrEnum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"
    ADMIN = "admin"


RoleLiteral = Literal["student", "instructor", "admin"]


class DocumentStatus(StrEnum):
    UPLOADED = "Uploaded"
    PROCESSING = "Processing"
    READY = "Ready"
    FAILED = "Failed"


DocumentStatusLiteral = Literal["Uploaded", "Processing", "Ready", "Failed"]


class Difficulty(StrEnum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"


DifficultyLiteral = Literal["Easy", "Medium", "Hard"]


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


ReviewStatusLiteral = Literal["pending", "approved", "rejected"]


class GenerationMode(StrEnum):
    LIVE = "live"
    MOCK = "mock"


GenerationModeLiteral = Literal["live", "mock"]


class ExamMode(StrEnum):
    PRACTICE = "practice"
    GRADED = "graded"


ExamModeLiteral = Literal["practice", "graded"]


class ExamStateEnum(StrEnum):
    CREATED = "Created"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    GRADED = "Graded"


ExamStateLiteral = Literal["Created", "InProgress", "Completed", "Graded"]


class CompletionReason(StrEnum):
    TARGET_REACHED = "target_reached"
    USER_FINISHED = "user_finished"
    POOL_EXHAUSTED = "pool_exhausted"


CompletionReasonLiteral = Literal["target_reached", "user_finished", "pool_exhausted"]
