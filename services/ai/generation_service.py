from __future__ import annotations

from uuid import UUID

from core.errors import ValidationError
from core.schemas import GenerationBatch, GenerationRequest
from services.ai.adapter import AIAdapter
from services.ai.mock_adapter import OfflineMockAIAdapter
from services.ai.validation import QuestionValidator


class QuestionGenerationService:
    """Application service orchestrating AI question generation and rigorous multi-stage validation."""

    def __init__(
        self,
        adapter: AIAdapter | None = None,
        validator: type[QuestionValidator] | None = None,
    ) -> None:
        self.adapter = adapter or OfflineMockAIAdapter()
        self.validator = validator or QuestionValidator

    async def generate(
        self,
        actor_id: UUID,
        request: GenerationRequest,
    ) -> GenerationBatch:
        """Generates, verifies, and returns a batch of grounded multiple-choice questions."""
        if not request.pages:
            raise ValidationError("GenerationRequest must include at least one extracted page.")

        if request.question_count < 1:
            raise ValidationError("question_count must be at least 1.")

        # Execute generation through configured adapter
        batch = await self.adapter.generate_questions(request)

        # Run 3-stage validation against source pages
        self.validator.validate_batch(batch, request.pages)

        return batch
