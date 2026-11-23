from __future__ import annotations

import random
import re
from datetime import UTC, datetime
from uuid import UUID, uuid5

from core.errors import InsufficientSourceContentError
from core.schemas import (
    ExtractedPage,
    GenerationBatch,
    GenerationRequest,
    QuestionPayload,
    QuestionSourceMeta,
)
from services.ai.adapter import AIAdapter

# Fixed namespace for seed-deterministic UUID generation
EXAMIFY_NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


class OfflineMockAIAdapter(AIAdapter):
    """Deterministic, seed-reproducible offline AI adapter.

    Generates strictly grounded multiple-choice questions using verbatim sentences
    extracted from the provided physical pages, guaranteeing traceable citations.
    """

    def __init__(self, provider_name: str = "offline-mock") -> None:
        self.provider_name = provider_name

    def _extract_sentences(
        self,
        pages: tuple[ExtractedPage, ...],
    ) -> list[tuple[int, str]]:
        """Extracts valid, non-trivial sentences mapped to their 1-indexed page number."""
        extracted: list[tuple[int, str]] = []
        for page in pages:
            raw_text = page.text.strip()
            if not raw_text:
                continue
            # Split text on sentence terminators or line breaks
            parts = re.split(r"(?<=[.!?])\s+|\n+", raw_text)
            for part in parts:
                clean_part = re.sub(r"\s+", " ", part).strip()
                # Accept substantive sentences of 25 to 250 characters with at least 4 words
                if 25 <= len(clean_part) <= 250 and len(clean_part.split()) >= 4:
                    extracted.append((page.page_number, clean_part))
        return extracted

    async def generate_questions(
        self,
        request: GenerationRequest,
    ) -> GenerationBatch:
        """Generates a deterministic batch of verified questions from document pages."""
        candidates = self._extract_sentences(request.pages)
        if not candidates:
            raise InsufficientSourceContentError(
                f"Document {request.document_id} contains no extractable sentences "
                f"across {len(request.pages)} pages."
            )

        rng = random.Random(request.seed)
        # Shuffle candidates deterministically
        shuffled_candidates = list(candidates)
        rng.shuffle(shuffled_candidates)

        target_count = request.question_count
        warnings: list[str] = []

        if len(shuffled_candidates) < target_count:
            warnings.append(
                f"Requested {target_count} questions, but source text only supports "
                f"{len(shuffled_candidates)} unique grounded questions."
            )
            count_to_generate = len(shuffled_candidates)
        else:
            count_to_generate = target_count

        questions: list[QuestionPayload] = []

        for idx in range(count_to_generate):
            page_num, correct_excerpt = shuffled_candidates[idx]

            # Choose topic from words in excerpt
            words = [
                w.strip(".,;:\"'()[]{}")
                for w in correct_excerpt.split()
                if len(w) > 4 and w.isalpha()
            ]
            topic = words[0].title() if words else "Core Concept"

            # Prepare distractors from remaining candidate sentences or perturbations
            other_sentences = [
                sent for p_num, sent in shuffled_candidates if sent != correct_excerpt
            ]
            distractors: list[str] = []
            if len(other_sentences) >= 3:
                # Deterministically sample 3 distinct distractors
                distractor_indices = [
                    (idx + offset + 1) % len(other_sentences) for offset in range(3)
                ]
                for d_idx in distractor_indices:
                    cand_d = other_sentences[d_idx]
                    if cand_d not in distractors and cand_d != correct_excerpt:
                        distractors.append(cand_d)

            # If not enough distinct sentences, create deterministic variants
            fallback_distractor_templates = [
                f"The text explicitly contradicts that {correct_excerpt[:50].lower()}...",
                f"Page {page_num} clarifies that this statement applies only under undefined conditions.",
                f"The documented specification invalidates {topic.lower()} assumptions.",
            ]
            for template in fallback_distractor_templates:
                if len(distractors) >= 3:
                    break
                if template not in distractors and template != correct_excerpt:
                    distractors.append(template)

            # Combine correct excerpt and distractors
            options_list = [correct_excerpt] + distractors[:3]
            # Ensure unique options
            seen: set[str] = set()
            unique_options: list[str] = []
            for opt in options_list:
                norm = " ".join(opt.split()).casefold()
                if norm not in seen:
                    seen.add(norm)
                    unique_options.append(opt)

            # Guarantee at least 2 options
            while len(unique_options) < 2:
                dummy = f"Alternative hypothesis {len(unique_options) + 1} for {topic}."
                if dummy.casefold() not in seen:
                    seen.add(dummy.casefold())
                    unique_options.append(dummy)

            # Shuffle options deterministically
            rng.shuffle(unique_options)
            correct_index = unique_options.index(correct_excerpt)

            # Deterministic question UUID based on document_id, seed, and question index
            q_id = uuid5(
                EXAMIFY_NAMESPACE,
                f"{request.document_id}-{request.seed}-{idx}",
            )

            prompt = (
                f"Based on the verified text on page {page_num}, "
                f"which of the following statements regarding '{topic}' is accurate?"
            )
            explanation = f'Verifiable source text on page {page_num}: "{correct_excerpt}"'

            source = QuestionSourceMeta(
                document_id=request.document_id,
                page_number=page_num,
                excerpt=correct_excerpt,
            )

            question = QuestionPayload(
                schema_version="1.0",
                question_id=q_id,
                question_type="multiple_choice",
                prompt=prompt,
                options=tuple(unique_options),
                correct_index=correct_index,
                difficulty=request.difficulty,
                explanation=explanation,
                topic=topic,
                sources=(source,),
                generation_mode="mock",
                provider=self.provider_name,
                created_at=datetime.now(UTC),
            )
            questions.append(question)

        return GenerationBatch(
            questions=tuple(questions),
            generation_mode="mock",
            provider=self.provider_name,
            fallback_reason=None,
            warnings=tuple(warnings),
        )
