from typing import Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field


class SendEmailRequest(BaseModel):
    to: EmailStr = Field(..., description="Recipient email address.")
    subject: str = Field(..., description="Subject of the email.")
    body: str = Field(..., description="Content of the email (HTML or plain text).")
    cc: Optional[EmailStr] = Field(
        None, description="Carbon copy recipient email address."
    )
    bcc: Optional[EmailStr] = Field(
        None, description="Blind carbon copy recipient email address."
    )


class SendEmailReplyRequest(SendEmailRequest):
    original_message_id: str = Field(
        ..., description="The ID of the original message to reply to."
    )


class EmailInfo(BaseModel):
    id: str = Field(..., description="The unique ID of the message.")
    threadId: str = Field(
        ..., description="The ID of the thread the message belongs to."
    )
    labelIds: List[str] = Field(
        [], description="List of labels applied to the message."
    )
    snippet: Optional[str] = Field(
        None, description="A short summary of the message text."
    )
    # Add other fields as needed, e.g., headers (From, To, Subject, Date)
    # This schema is for listing messages, not the full message content.


class FullEmailDetails(BaseModel):
    id: str
    threadId: str
    # Add more fields from Gmail API's full message response as needed
    # For now, let's keep it simple for content retrieval
    from_email: Optional[EmailStr] = None
    to_email: Optional[EmailStr] = None
    subject: Optional[str] = None
    date: Optional[str] = None


class SummarizeEmailRequest(BaseModel):
    message_id: str = Field(
        ..., description="The ID of the email message to summarize."
    )


class SummarizeEmailResponse(BaseModel):
    message_id: str
    summary: str
    original_content: Optional[str] = None
