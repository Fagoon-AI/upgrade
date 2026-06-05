from typing import List, Dict, Generator
from loguru import logger
import uuid

CHUNK_WORD_SIZE = 512
CHUNK_WORD_OVERLAP = 100

def custom_text_splitter(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    if not text:
        logger.warning("custom_text_splitter received empty text.")
        return []

    chunks = []
    start_index = 0
    text_length = len(text)

    while start_index < text_length:
        end_index = start_index + chunk_size
        chunk = text[start_index:end_index]
        chunks.append(chunk)
        start_index += chunk_size - chunk_overlap

    logger.info(f"Custom splitter created {len(chunks)} chunks.")
    return chunks

def _get_all_words_from_pages(pages_with_words: List[Dict]) -> Generator[Dict, None, None]:
    """Generator to yield all words from parsed pages with their page number."""
    for page in pages_with_words:
        for word in page["words"]:
            word['page_no'] = page['page_no']
            yield word

def chunk_pdf_from_words(pages_with_words: List[Dict], document_id: str) -> List[Dict]:
    """
    OPTIMIZED: Chunks a document from word objects with a target size and overlap.
    This version is more robust and handles the final chunk cleanly.
    """
    logger.info(f"Chunking PDF with word size={CHUNK_WORD_SIZE} and overlap={CHUNK_WORD_OVERLAP}.")

    all_words = list(_get_all_words_from_pages(pages_with_words))
    total_words = len(all_words)

    if not all_words:
        logger.warning(f"No words extracted from document {document_id}. Returning empty list.")
        return []

    all_chunks = []
    start_index = 0
    chunk_index = 1

    while start_index < total_words:
        end_index = start_index + CHUNK_WORD_SIZE

        if (total_words - end_index) > 0 and (total_words - end_index) < CHUNK_WORD_OVERLAP:
            end_index = total_words

        segment_words = all_words[start_index:end_index]
        if not segment_words:
            break

        chunk_text = " ".join([w["text"] for w in segment_words])
        first_word = segment_words[0]
        page_no = first_word['page_no']

        all_chunks.append({
            "chunk_id": str(uuid.uuid4()),
            "document_id": document_id,
            "text": chunk_text,
            "metadata": {
                "source": document_id,
                "page_no": page_no,
                "chunk_key": f"p{page_no}.{chunk_index}",
                "word_count": len(segment_words),
            }
        })
        chunk_index += 1

        if end_index >= total_words:
            break

        start_index += (CHUNK_WORD_SIZE - CHUNK_WORD_OVERLAP)

    logger.success(f"Generated {len(all_chunks)} intelligent, overlapping chunks from PDF.")
    return all_chunks


def chunk_text_content(text: str, document_id: str) -> List[Dict]:
    """
    Chunks plain text from sources like web pages using the custom splitter.
    """
    logger.info(f"Chunking plain text content of length {len(text)} for document '{document_id}'...")
    if not text: return []

    chunk_size = 512
    chunk_overlap = 100

    docs = custom_text_splitter(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = []

    for i, doc in enumerate(docs):
        chunks.append({
            "chunk_id": str(uuid.uuid4()),
            "document_id": document_id,
            "text": doc,
            "metadata": {
                "source": document_id,
                "page_no": 1,
                "chunk_key": f"p1.{i+1}",
                "word_count": len(doc.split()),
            }
        })

    logger.success(f"Generated {len(chunks)} chunks from plain text using custom splitter.")
    return chunks