from __future__ import annotations

import re
from uuid import UUID

from core.errors import ValidationError
from core.schemas import ExtractedPage, GenerationBatch, QuestionPayload


class QuestionValidator:
    """Three-stage validator for AI-generated question payloads.

    Stage 1: Schema & internal invariants (Pydantic model integrity, bounds, uniqueness).
    Stage 2: Document & page-bounds checking (verifies cited pages exist in extracted pages).
    Stage 3: Substring excerpt grounding (ensures source citations verbatim match page text).
    """

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalizes text by collapsing whitespace sequences and casefolding."""
        return re.sub(r"\s+", " ", text).strip().casefold()

    @classmethod
    def validate_stage1_schema(cls, question: QuestionPayload) -> None:
        """Stage 1: Validates question schema invariants."""
        if not isinstance(question, QuestionPayload):
            raise ValidationError(
                f"Expected QuestionPayload instance, got {type(question).__name__}"
            )
        if question.correct_index >= len(question.options):
            raise ValidationError(
                f"Question {question.question_id}: correct_index {question.correct_index} "
                f"out of bounds for {len(question.options)} options."
            )
        if len(question.sources) < 1:
            raise ValidationError(
                f"Question {question.question_id}: requires at least one source citation."
            )

    @classmethod
    def validate_stage2_page_bounds(
        cls,
        question: QuestionPayload,
        valid_pages: set[int],
        expected_document_id: UUID | None = None,
    ) -> None:
        """Stage 2: Validates cited pages belong to the document and exist in extracted pages."""
        for idx, source in enumerate(question.sources):
            if expected_document_id and source.document_id != expected_document_id:
                raise ValidationError(
                    f"Question {question.question_id} source #{idx}: document_id mismatch "
                    f"({source.document_id} != {expected_document_id})."
                )
            if source.page_number not in valid_pages:
                raise ValidationError(
                    f"Question {question.question_id} source #{idx}: cited page {source.page_number} "
                    f"does not exist in document pages {sorted(valid_pages)}."
                )

    @classmethod
    def validate_stage3_excerpt_grounding(
        cls,
        question: QuestionPayload,
        page_texts: dict[int, str],
    ) -> None:
        """Stage 3: Verifies that cited excerpts occur verbatim in normalized page text."""
        for idx, source in enumerate(question.sources):
            page_text = page_texts.get(source.page_number, "")
            norm_excerpt = cls.normalize_text(source.excerpt)
            norm_page_text = cls.normalize_text(page_text)

            if not norm_excerpt:
                raise ValidationError(
                    f"Question {question.question_id} source #{idx}: excerpt cannot be empty."
                )

            if norm_excerpt not in norm_page_text:
                raise ValidationError(
                    f"Question {question.question_id} source #{idx}: excerpt does not match "
                    f"the extracted text on page {source.page_number}. "
                    f"Excerpt: '{source.excerpt[:80]}...'"
                )

    @classmethod
    def validate_question(
        cls,
        question: QuestionPayload,
        pages: tuple[ExtractedPage, ...],
    ) -> None:
        """Executes all 3 validation stages sequentially for a question against source pages."""
        cls.validate_stage1_schema(question)

        valid_pages = {page.page_number for page in pages}
        expected_doc_id = pages[0].document_id if pages else None
        cls.validate_stage2_page_bounds(question, valid_pages, expected_doc_id)

        page_texts = {page.page_number: page.text for page in pages}
        cls.validate_stage3_excerpt_grounding(question, page_texts)

    @classmethod
    def validate_batch(
        cls,
        batch: GenerationBatch,
        pages: tuple[ExtractedPage, ...],
    ) -> None:
        """Validates all questions in a generation batch against extracted source pages."""
        for question in batch.questions:
            cls.validate_question(question, pages)
