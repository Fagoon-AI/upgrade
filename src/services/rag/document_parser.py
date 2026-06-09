from typing import List, Dict
import pdfplumber
from loguru import logger
from io import BytesIO

def parse_pdf_with_coordinates(file_bytes: bytes) -> List[Dict]:
    """
    Extracts pages and word-level objects (text + coordinates) from a PDF file's bytes.
    """
    pages_with_words = []
    logger.info("Starting PDF parsing with coordinate extraction...")
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                words = page.extract_words(x_tolerance=2, y_tolerance=2, use_text_flow=True)
                page_data = {
                    "page_no": i,
                    "words": [
                        {
                            "text": w["text"],
                            "x0": w["x0"], "top": w["top"],
                            "x1": w["x1"], "bottom": w["bottom"],
                        }
                        for w in words
                    ],
                }
                pages_with_words.append(page_data)
        logger.success("Successfully parsed {} pages from PDF.", len(pages_with_words))
        return pages_with_words
    except Exception as e:
        logger.error("Failed to parse PDF for word-level data: {}", e, exc_info=True)
        return []

def parse_text(content: str) -> str:
    """
    Cleans plain text content from sources like web pages.
    """
    cleaned_text = " ".join(content.split())
    logger.info("Parsed and cleaned text content, final length: {} chars.", len(cleaned_text))
    return cleaned_text