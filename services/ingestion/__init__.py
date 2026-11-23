"""Ingestion service package: PDF and plain text extraction with 1-indexed physical pages."""

from services.ingestion.extractor import ContentExtractionService

__all__ = ["ContentExtractionService"]
