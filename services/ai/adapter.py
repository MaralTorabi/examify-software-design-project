from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.schemas import GenerationBatch, GenerationRequest


@dataclass(frozen=True)
class FallbackPolicy:
    """Policy governing when and how a primary AI adapter falls back to an offline adapter."""

    allow_mock_fallback: bool = True
    max_retries: int = 1
    catch_network_errors: bool = True
    catch_validation_errors: bool = True


class AIAdapter(ABC):
    """Abstract interface for AI question generation adapters."""

    @abstractmethod
    async def generate_questions(
        self,
        request: GenerationRequest,
    ) -> GenerationBatch:
        """Generates a batch of questions from extracted document pages."""
        ...
