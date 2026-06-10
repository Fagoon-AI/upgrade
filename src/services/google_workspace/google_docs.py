from typing import Dict, List, Optional
from loguru import logger
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GoogleDocsService:
    def __init__(self, credentials: Credentials):
        """
        Initializes the Google Docs API service.
        Args:
            credentials: The google.oauth2.credentials.Credentials object.
        """
        self.credentials = credentials
        self._service = None

    @property
    def service(self):
        """
        Returns the Docs API service client, building it if it doesn't exist.
        """
        if self._service is None:
            try:
                # Use "docs" API
                self._service = build("docs", "v1", credentials=self.credentials)
                logger.info("Google Docs API service built successfully.")
            except Exception as e:
                logger.error(
                    f"Error building Google Docs API service: {e}", exc_info=True
                )
                raise HttpError(f"Could not build Docs service: {e}")
        return self._service

    async def get_document_content(self, document_id: str) -> Dict:
        """
        Retrieves the full content of a Google Docs document.
        Args:
            document_id (str): The ID of the Google Docs document.
        Returns:
            Dict: The full document structure from the Docs API.
        Raises:
            HttpError: If the Docs API call fails.
        """
        try:
            document = self.service.documents().get(documentId=document_id).execute()
            logger.info(f"Retrieved Google Doc with ID: {document_id}")
            return document
        except HttpError as error:
            logger.error(
                f"Failed to retrieve Google Doc {document_id}: {error}", exc_info=True
            )
            raise

    async def extract_text_from_document(self, document_id: str) -> str:
        """
        Extracts plain text content from a Google Docs document.
        Combines text from paragraphs, tables, and other structural elements.
        """
        document = await self.get_document_content(document_id)
        content_elements = document.get("body", {}).get("content", [])

        doc_text = []

        def read_paragraph_element(element):
            """Returns the text in the given ParagraphElement.
            Taken from Google Docs API examples.
            """
            text_run = element.get("textRun")
            if not text_run:
                return ""
            return text_run.get("content")

        for element in content_elements:
            if "paragraph" in element:
                paragraph = element.get("paragraph")
                for paragraph_element in paragraph.get("elements", []):
                    doc_text.append(read_paragraph_element(paragraph_element))
            elif "table" in element:
                table = element.get("table")
                for row in table.get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        for content_item in cell.get("content", []):
                            if "paragraph" in content_item:
                                for paragraph_element in content_item["paragraph"].get(
                                    "elements", []
                                ):
                                    doc_text.append(
                                        read_paragraph_element(paragraph_element)
                                    )
            # Add more content types as needed (e.g., sectionBreak, embeddedObject, etc.)

        return "".join(doc_text)

    async def create_document(self, title: str, initial_content: Optional[str] = None) -> Dict:
        """
        Creates a new Google Docs document.
        Args:
            title (str): The title of the new document.
            initial_content (str): Optional initial text content for the document.
        Returns:
            Dict: Metadata of the created document.
        Raises:
            HttpError: If the Docs API call fails.
        """
        document_body = {"title": title}

        try:
            document = self.service.documents().create(body=document_body).execute()
            logger.info(f"Created Google Doc '{title}' with ID: {document.get('documentId')}")

            if initial_content:
                await self.write_to_document(
                    document_id=document.get("documentId"),
                    text=initial_content,
                    index=1,
                    delete_existing=False
                )
                logger.info(f"Added initial content to new document {document.get('documentId')} at index 1.")

            return document
        except HttpError as error:
            logger.error("Failed to create Google Doc '{}': {}", title, error, exc_info=True)
            raise

    async def write_to_document(
            self,
            document_id: str,
            text: str,
            index: Optional[int] = None,
            delete_existing: bool = False,
    ) -> Dict:
        """
        Writes text content to a Google Docs document.
        Args:
            document_id (str): The ID of the document to modify.
            text (str): The text content to write.
            index (int): The starting index where to insert the text.
                         If None, appends to the end. Use 1 for start of document.
            delete_existing (bool): If True, deletes all existing content before writing.
        Returns:
            Dict: The response from the Docs API batch update operation.
        Raises:
            HttpError: If the Docs API call fails.
        """
        requests = []

        if delete_existing:
            current_doc = await self.get_document_content(document_id)
            end_index = 0
            if current_doc.get("body", {}).get("content"):
                last_element = current_doc["body"]["content"][-1]
                end_index = last_element.get("endIndex", 0)
            if end_index > 1:
                requests.append({
                    "deleteContentRange": {
                        "range": {
                            "segmentId": "",
                            "startIndex": 1,
                            "endIndex": end_index
                        }
                    }
                })
            effective_index = 1
        else:
            if index is None:
                current_doc = await self.get_document_content(document_id)
                content = current_doc.get("body", {}).get("content", [])
                if content:
                    effective_index = content[-1].get("endIndex", 1)
                else:
                    effective_index = 1
            else:
                effective_index = index

        requests.append(
            {
                "insertText": {
                    "location": {
                        "segmentId": "",
                        "index": effective_index,
                    },
                    "text": text,
                }
            }
        )

        try:
            result = (
                self.service.documents()
                .batchUpdate(documentId=document_id, body={"requests": requests})
                .execute()
            )
            logger.info(f"Wrote content to Google Doc {document_id}.")
            return result
        except HttpError as error:
            logger.error(
                f"Failed to write content to Google Doc {document_id}: {error}",
                exc_info=True,
            )
            raise
