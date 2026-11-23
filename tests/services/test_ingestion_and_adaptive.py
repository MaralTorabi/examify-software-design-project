from __future__ import annotations

import io
from uuid import uuid4

import pypdf
import pytest

from core.errors import InsufficientSourceContentError
from core.schemas import QuestionPayload, QuestionSourceMeta
from core.types import Difficulty
from services.adaptive.engine import AdaptiveQuestionSelector
from services.adaptive.strategies import (
    ConsecutiveAnswersStrategy,
    PerformanceSnapshot,
    RollingAccuracyStrategy,
)
from services.ingestion.extractor import ContentExtractionService


def test_extraction_from_pasted_text() -> None:
    svc = ContentExtractionService()
    doc_id = uuid4()
    raw_text = (
        "First chapter of the book.\n\n"
        "Second paragraph with critical architectural definitions.\n\n"
        "Third paragraph concluding page one."
    )
    pages = svc.extract_from_text(doc_id, raw_text)
    assert len(pages) >= 1
    assert pages[0].document_id == doc_id
    assert pages[0].page_number == 1
    assert "First chapter" in pages[0].text


def test_extraction_from_pasted_text_page_breaks() -> None:
    svc = ContentExtractionService()
    doc_id = uuid4()
    raw_text = "Page 1 Content\x0cPage 2 Content\x0cPage 3 Content"
    pages = svc.extract_from_text(doc_id, raw_text)
    assert len(pages) == 3
    assert pages[0].page_number == 1
    assert pages[1].page_number == 2
    assert pages[2].page_number == 3


def test_extraction_from_text_empty_raises() -> None:
    svc = ContentExtractionService()
    with pytest.raises(InsufficientSourceContentError):
        svc.extract_from_text(uuid4(), "   \n\t  ")


def test_extraction_from_bytes_txt() -> None:
    svc = ContentExtractionService()
    doc_id = uuid4()
    content = b"Sample text content from uploaded text file."
    pages = svc.extract_from_bytes(doc_id, "notes.txt", content)
    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert "Sample text content" in pages[0].text


def test_extraction_from_bytes_pdf_blank() -> None:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72, height=72)
    stream = io.BytesIO()
    writer.write(stream)
    pdf_bytes = stream.getvalue()

    svc = ContentExtractionService()
    doc_id = uuid4()
    with pytest.raises(InsufficientSourceContentError):
        svc.extract_from_bytes(doc_id, "blank.pdf", pdf_bytes)


def test_sha256_computation() -> None:
    svc = ContentExtractionService()
    data = b"Examify Verification Bytes"
    h1 = svc.compute_sha256(data)
    assert len(h1) == 64
    assert h1 == svc.compute_sha256(data)


def test_consecutive_answers_strategy() -> None:
    strat = ConsecutiveAnswersStrategy()
    snap_promote = PerformanceSnapshot(answered_count=2, recent_correctness=(True, True))
    assert strat.next_difficulty(Difficulty.EASY, snap_promote) == Difficulty.MEDIUM

    snap_demote = PerformanceSnapshot(answered_count=2, recent_correctness=(False, False))
    assert strat.next_difficulty(Difficulty.HARD, snap_demote) == Difficulty.MEDIUM


def test_rolling_accuracy_strategy() -> None:
    strat = RollingAccuracyStrategy(window_size=5)
    snap_high = PerformanceSnapshot(answered_count=5, recent_correctness=(True, True, True, True, False))
    assert strat.next_difficulty(Difficulty.EASY, snap_high) == Difficulty.MEDIUM

    snap_low = PerformanceSnapshot(answered_count=5, recent_correctness=(False, False, False, False, True))
    assert strat.next_difficulty(Difficulty.MEDIUM, snap_low) == Difficulty.EASY


def test_adaptive_question_selector_tie_breaking() -> None:
    selector = AdaptiveQuestionSelector()
    doc_id = uuid4()
    src = QuestionSourceMeta(document_id=doc_id, page_number=1, excerpt="Source excerpt")
    from datetime import UTC, datetime

    q_easy = QuestionPayload(
        question_id=uuid4(),
        prompt="Easy Q",
        options=("A", "B"),
        correct_index=0,
        difficulty=Difficulty.EASY,
        explanation="Expl",
        topic="General",
        sources=(src,),
        generation_mode="mock",
        provider="mock",
        created_at=datetime.now(UTC),
    )
    q_hard = QuestionPayload(
        question_id=uuid4(),
        prompt="Hard Q",
        options=("A", "B"),
        correct_index=0,
        difficulty=Difficulty.HARD,
        explanation="Expl",
        topic="General",
        sources=(src,),
        generation_mode="mock",
        provider="mock",
        created_at=datetime.now(UTC),
    )

    pool = [q_easy, q_hard]
    used_ids: set[uuid4] = set()

    # Target is Medium -> tie broken toward EASIER
    chosen = selector.select_next_question(pool, used_ids, Difficulty.MEDIUM)
    assert chosen is not None
    assert chosen.difficulty == Difficulty.EASY
