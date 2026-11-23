"""AI subsystem package: adapters, validation, and generation orchestration."""

from services.ai.adapter import AIAdapter, FallbackPolicy
from services.ai.fallback_adapter import FallbackAIAdapter
from services.ai.generation_service import QuestionGenerationService
from services.ai.mock_adapter import OfflineMockAIAdapter
from services.ai.validation import QuestionValidator

__all__ = [
    "AIAdapter",
    "FallbackPolicy",
    "OfflineMockAIAdapter",
    "FallbackAIAdapter",
    "QuestionValidator",
    "QuestionGenerationService",
]
