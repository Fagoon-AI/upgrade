import asyncio
from pathlib import Path
from typing import IO, Any, List, Union
from loguru import logger
from pypdf import PdfReader as DocumentReader
from pypdf.errors import PdfStreamError

from src.schemas.document import Document


class BasePDFReader:
    def __init__(self, chunk_size: int = 1000, overlap: int = 100):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_document(self, document: Document) -> List[Document]:
        return self.__chunk_document(document)

    def clean_text(self, text: str) -> str:
        import re

        # Fix line breaks where words are broken by newlines
        text = re.sub(
            r"(?<!\n)\n(?!\n)", " ", text
        )  # Replace single newlines (line wraps) with space

        # Normalize paragraph breaks: ensure exactly two newlines between paragraphs
        text = re.sub(r"\n{2,}", "\n\n", text)

        # Collapse extra whitespace
        text = re.sub(r"[ \t]+", " ", text)

        return text.strip()

    def __chunk_document(self, document: Document) -> List[Document]:
        """
        Industry-standard document chunking:
        - Fixed character chunk size
        - With context overlap
        - No smart boundary logic (simple, scalable, robust)
        """
        content = self.clean_text(document.content)
        chunked_documents: List[Document] = []

        chunk_number = 1
        start = 0
        content_length = len(content)

        while start < content_length:
            end = min(start + self.chunk_size, content_length)
            chunk = content[start:end].strip()

            if chunk:  # Ensure the chunk has content
                metadata = document.metadata.copy()
                metadata["chunk"] = chunk_number
                metadata["chunk_size"] = len(chunk)

                chunk_id = f"{document.id or document.name}_{chunk_number}"
                chunked_documents.append(
                    Document(
                        id=chunk_id,
                        name=document.name,
                        metadata=metadata,
                        content=chunk,
                    )
                )

                chunk_number += 1

            start += self.chunk_size - self.overlap  # Advance with overlap

        return chunked_documents

    def _build_chunked_documents(self, documents: List[Document]) -> List[Document]:
        chunked_documents: List[Document] = []
        for document in documents:
            chunked_documents.extend(self.chunk_document(document))
        return chunked_documents


class PDFReader(BasePDFReader):
    """Reader for PDF files"""

    chunk: bool = True

    def read(self, pdf: Union[str, Path, IO[Any]]) -> List[Document]:
        try:
            if isinstance(pdf, str):
                doc_name = pdf.split("/")[-1].split(".")[0].replace(" ", "_")
            else:
                doc_name = pdf.name.split(".")[0]
        except Exception:
            doc_name = "pdf"

        logger.debug("Reading: {}", doc_name)

        try:
            doc_reader = DocumentReader(pdf)
        except PdfStreamError as e:
            logger.error("Error reading PDF: {}", e)
            return []

        documents = []
        for page_number, page in enumerate(doc_reader.pages, start=1):
            documents.append(
                Document(
                    name=doc_name,
                    id=f"{doc_name}_{page_number}",
                    metadata={"page": page_number},
                    content=page.extract_text(),
                )
            )
        if self.chunk:
            return self._build_chunked_documents(documents)
        return documents

    async def extract(self, pdf: Union[str, Path, IO[Any]]) -> List[Document]:
        try:
            if isinstance(pdf, str):
                doc_name = pdf.split("/")[-1].split(".")[0].replace(" ", "_")
            else:
                doc_name = pdf.name.split(".")[0]
        except Exception:
            doc_name = "pdf"

        logger.debug("Reading: {}", doc_name)

        try:
            doc_reader = DocumentReader(pdf)
        except PdfStreamError as e:
            logger.error("Error reading PDF: {}", e)
            return []

        async def _process_document(
            doc_name: str, page_number: int, page: Any
        ) -> Document:
            return Document(
                name=doc_name,
                id=f"{doc_name}_{page_number}",
                metadata={"page": page_number},
                content=page.extract_text(),
            )

        # Process pages in parallel using asyncio.gather
        documents = await asyncio.gather(
            *[
                _process_document(doc_name, page_number, page)
                for page_number, page in enumerate(doc_reader.pages, start=1)
            ]
        )

        if self.chunk:
            return self._build_chunked_documents(documents)
        return documents
