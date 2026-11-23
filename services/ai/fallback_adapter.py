from __future__ import annotations

import logging

from core.errors import ExamifyError, ValidationError
from core.schemas import GenerationBatch, GenerationRequest
from services.ai.adapter import AIAdapter, FallbackPolicy

logger = logging.getLogger(__name__)


class FallbackAIAdapter(AIAdapter):
    """Decorator/Composite AIAdapter that wraps a primary adapter and falls back to a secondary adapter."""

    def __init__(
        self,
        primary: AIAdapter,
        fallback: AIAdapter,
        policy: FallbackPolicy | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.policy = policy or FallbackPolicy()

    def _is_recoverable_failure(self, exc: Exception) -> bool:
        """Determines if the failure is eligible for fallback per architectural policy."""
        # Critical programming errors must be propagated directly
        if isinstance(
            exc, (TypeError, AttributeError, NameError, SyntaxError, NotImplementedError)
        ):
            return False

        # Domain validation errors from ill-formed external responses
        if isinstance(exc, ValidationError) and self.policy.catch_validation_errors:
            return True

        # Network / HTTP / Timeout / Provider errors
        if self.policy.catch_network_errors:
            # Matches httpx.HTTPError, TimeoutError, ConnectionError, etc.
            exc_module = exc.__class__.__module__
            if "httpx" in exc_module or isinstance(exc, (TimeoutError, ConnectionError, OSError)):
                return True

        # Any general Examify operational error
        if isinstance(exc, ExamifyError):
            return True

        # Fallback allowed for standard runtime provider failures
        return isinstance(exc, RuntimeError)

    async def generate_questions(
        self,
        request: GenerationRequest,
    ) -> GenerationBatch:
        """Attempts generation with primary adapter, falling back to secondary if permitted."""
        try:
            batch = await self.primary.generate_questions(request)
            return batch
        except Exception as exc:
            if not self.policy.allow_mock_fallback or not self._is_recoverable_failure(exc):
                logger.error("Primary AI adapter failed unrecoverably: %s", exc)
                raise

            fallback_reason = f"Primary provider failed with {exc.__class__.__name__}: {str(exc).strip() or 'Unknown error'}"
            logger.warning("Activating fallback AI adapter. Reason: %s", fallback_reason)

            fallback_batch = await self.fallback.generate_questions(request)

            # Return fallback batch with persisted fallback_reason
            return GenerationBatch(
                questions=fallback_batch.questions,
                generation_mode=fallback_batch.generation_mode,
                provider=fallback_batch.provider,
                fallback_reason=fallback_reason,
                warnings=fallback_batch.warnings + (f"Fallback activated: {fallback_reason}",),
            )
