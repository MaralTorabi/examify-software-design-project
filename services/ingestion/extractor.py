from __future__ import annotations

import hashlib
import io
import re
from uuid import UUID

import pypdf

from core.errors import InsufficientSourceContentError, ValidationError
from core.schemas import ExtractedPage


class ContentExtractionService:
    """Extracts verifiable, physical 1-indexed page text from raw text and document bytes."""

    PAGE_CHAR_LIMIT: int = 2500

    @staticmethod
    def compute_sha256(content: bytes) -> str:
        """Computes lowercase SHA-256 hex digest for binary content."""
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def compute_text_sha256(text: str) -> str:
        """Computes lowercase SHA-256 hex digest for string content."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def extract_from_text(
        self,
        document_id: UUID,
        raw_text: str,
    ) -> tuple[ExtractedPage, ...]:
        """Extracts 1-indexed ExtractedPage objects from pasted plain text."""
        cleaned_text = raw_text.strip()
        if not cleaned_text:
            raise InsufficientSourceContentError(
                f"Document {document_id} has empty content; cannot extract pages."
            )

        # Check for explicit form-feed/page-break markers
        if "\x0c" in cleaned_text or "\f" in cleaned_text:
            raw_pages = [p.strip() for p in re.split(r"[\x0c\f]", cleaned_text)]
            raw_pages = [p for p in raw_pages if p]
        else:
            # Split into chunks of sensible length preserving paragraphs
            paragraphs = [p.strip() for p in cleaned_text.split("\n\n") if p.strip()]
            raw_pages = []
            current_page_parts: list[str] = []
            current_len = 0

            for para in paragraphs:
                if current_len + len(para) > self.PAGE_CHAR_LIMIT and current_page_parts:
                    raw_pages.append("\n\n".join(current_page_parts))
                    current_page_parts = [para]
                    current_len = len(para)
                else:
                    current_page_parts.append(para)
                    current_len += len(para) + 2

            if current_page_parts:
                raw_pages.append("\n\n".join(current_page_parts))

        if not raw_pages:
            raw_pages = [cleaned_text]

        pages = tuple(
            ExtractedPage(
                document_id=document_id,
                page_number=page_idx + 1,  # 1-indexed physical page
                text=page_str,
            )
            for page_idx, page_str in enumerate(raw_pages)
        )
        return pages

    def extract_from_bytes(
        self,
        document_id: UUID,
        filename: str,
        content: bytes,
    ) -> tuple[ExtractedPage, ...]:
        """Extracts 1-indexed ExtractedPage objects from .pdf or .txt file bytes."""
        if not content:
            raise InsufficientSourceContentError(
                f"Document {document_id} ({filename}) is empty (0 bytes)."
            )

        lower_name = filename.lower()
        if lower_name.endswith(".txt"):
            try:
                decoded_text = content.decode("utf-8")
            except UnicodeDecodeError:
                decoded_text = content.decode("latin-1")
            return self.extract_from_text(document_id, decoded_text)

        if lower_name.endswith(".pdf"):
            try:
                stream = io.BytesIO(content)
                reader = pypdf.PdfReader(stream)
            except Exception as exc:
                raise ValidationError(
                    f"Failed to parse PDF document {filename}: {exc}",
                    code="CORRUPT_PDF",
                ) from exc

            if reader.is_encrypted:
                raise ValidationError(
                    f"Document {filename} is password-protected/encrypted.",
                    code="ENCRYPTED_PDF",
                )

            total_pages = len(reader.pages)
            if total_pages == 0:
                raise InsufficientSourceContentError(
                    f"PDF document {filename} contains 0 physical pages."
                )

            extracted_pages: list[ExtractedPage] = []
            total_extracted_chars = 0

            for page_idx, page in enumerate(reader.pages):
                page_number = page_idx + 1  # 1-indexed physical page
                try:
                    page_text = page.extract_text() or ""
                except Exception:
                    page_text = ""

                cleaned = page_text.strip()
                total_extracted_chars += len(cleaned)
                extracted_pages.append(
                    ExtractedPage(
                        document_id=document_id,
                        page_number=page_number,
                        text=cleaned,
                    )
                )

            if total_extracted_chars == 0:
                raise InsufficientSourceContentError(
                    f"PDF document {filename} contains no extractable text across "
                    f"{total_pages} pages (scanned image PDFs require OCR)."
                )

            return tuple(extracted_pages)

        raise ValidationError(
            f"Unsupported file format '{filename}'. Supported formats are .pdf and .txt.",
            code="UNSUPPORTED_MEDIA_TYPE",
        )
