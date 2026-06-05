from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class DocDetails(BaseModel):
    document_id: str = Field(
        ...,
        alias="documentId",
        description="The unique ID of the Google Docs document.",
    )
    title: str = Field(..., description="The title of the document.")
    revision_id: str = Field(
        ..., alias="revisionId", description="The revision ID of the document."
    )
    # Add more fields like 'suggestionsViewMode', 'namedRanges', etc., as needed

    class Config:
        validate_by_name = True


class CreateDocRequest(BaseModel):
    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="The title for the new Google Docs document.",
    )
    initial_content: Optional[str] = Field(
        None, description="Optional initial text content for the new document."
    )


class WriteDocRequest(BaseModel):
    document_id: str = Field(
        ..., description="The ID of the Google Docs document to modify."
    )
    text_content: str = Field(
        ..., description="The text content to write to the document."
    )
    insert_index: Optional[int] = Field(
        None,
        ge=1,
        description="The 1-based index where to insert the text. If omitted, text is appended.",
    )
    delete_existing_content: bool = Field(
        False,
        description="If true, deletes all existing content in the document before writing the new text.",
    )


class DocContentResponse(BaseModel):
    document_id: str
    title: str
    content: str = Field(..., description="The plain text content of the document.")
