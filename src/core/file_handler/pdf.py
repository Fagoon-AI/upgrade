from typing import List
from loguru import logger
from pypdf import PdfReader as DocumentReader 
from pypdf.errors import PdfStreamError
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from src.utils.common import get_bytes_stream
from src.schemas.document import PageData



class PDFExtractionError(Exception):
    """Custom exception for PDF extraction-related failures."""


class PDFDocumentExtractor:
    """Extracts text and metadata from a PDF file."""

    def __init__(self, file_bytes: bytes) -> None:
        if not file_bytes:
            logger.error("Initialization failed: file_bytes is empty.")
            raise ValueError("file_bytes must not be empty")

        self._file_bytes = file_bytes
        logger.debug("PDFDocumentExtractor initialized.")

    async def extract_pages(self) -> List[PageData]:
        """Asynchronously extracts text and metadata from all pages in the PDF."""
        return await run_in_threadpool(self._extract_pages_sync)

    def _extract_pages_sync(self) -> List[PageData]:
        try:
            with get_bytes_stream(self._file_bytes) as pdf_stream:
                reader = DocumentReader(pdf_stream)
                logger.info("PDF stream opened successfully.")
                return self._extract_all_pages(reader)

        except PdfStreamError as e:
            logger.exception("Failed to read PDF stream.")
            raise PDFExtractionError(f"Failed to read PDF content: {e}") from e

        except Exception as e:
            logger.exception("Unexpected error during PDF extraction.")
            raise PDFExtractionError(f"Unexpected error: {e}") from e

    def _extract_all_pages(self, reader: DocumentReader) -> List[PageData]:
        pages_data = []
        total_pages = len(reader.pages)
        logger.debug(f"Starting extraction of {total_pages} pages.")

        for i, page in enumerate(reader.pages, start=1):
            try:
                page_data = self._extract_single_page(i, page)
                pages_data.append(page_data)
                logger.debug(f"Page {i} extracted successfully.")
            except ValidationError as ve:
                logger.error(f"Validation failed for page {i}: {ve}")
            except Exception as e:
                logger.warning(f"Failed to extract page {i}: {e}")

        logger.info(f"Extraction completed for {len(pages_data)} pages.")
        return pages_data

    def _extract_single_page(self, page_number: int, page) -> PageData:
        text = page.extract_text() or ""
        rotation = page.get("/Rotate") or 0
        media_box = page.mediabox

        return PageData(
            content=text,
            metadata={
                "page_number": page_number,
                "rotation": rotation,
                "width_pts": float(media_box.width),
                "height_pts": float(media_box.height),
            },
        )
