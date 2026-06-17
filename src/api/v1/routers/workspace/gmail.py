from typing import List, Optional
from loguru import logger
from fastapi import APIRouter, Depends, HTTPException, Query, status
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

import uuid
from .deps import get_google_credentials, get_current_user
from src.models.auth_models.user_model import UserInDB
from src.schemas.workspace.common import Message
from src.schemas.workspace.gmail import (EmailInfo, FullEmailDetails,
                               SendEmailReplyRequest, SendEmailRequest,
                               SummarizeEmailRequest, SummarizeEmailResponse)
from src.services.google_workspace.ai_service import AIService
from src.services.google_workspace.google_gmail import GoogleGmailService


router = APIRouter()

async def get_gmail_service(
    credentials: Credentials = Depends(get_google_credentials),
) -> GoogleGmailService:
    return GoogleGmailService(credentials)


async def get_ai_service(current_user: UserInDB = Depends(get_current_user)) -> AIService:
    user_uuid = uuid.UUID(str(current_user.id)) if current_user else None
    return AIService(user_id=user_uuid)


@router.post(
    "/send-email",
    response_model=Message,
    status_code=status.HTTP_200_OK,
    summary="Send a new email",
)
async def send_email(
    request: SendEmailRequest,
    gmail_service: GoogleGmailService = Depends(get_gmail_service),
):
    """
    Sends a new email on behalf of the authenticated user.
    """
    try:
        sent_message = await gmail_service.send_email(
            to=request.to,
            subject=request.subject,
            body=request.body,
            cc=request.cc,
            bcc=request.bcc,
        )
        return {
            "message": f"Email sent successfully. Message ID: {sent_message.get('id')}"
        }
    except HttpError as e:
        error_msg = e.content.decode() if e.content else e
        logger.error(
            "Gmail API error sending email: {}",
            error_msg,
            exc_info=True,
        )
        raise HTTPException(
            status_code=(
                e.resp.status
                if hasattr(e, "resp")
                else status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=f"Failed to send email: {error_msg}",
        )
    except Exception as e:
        logger.error("Unexpected error sending email: {}", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while sending email.",
        )


@router.post(
    "/reply-email",
    response_model=Message,
    status_code=status.HTTP_200_OK,
    summary="Reply to an existing email",
)
async def reply_email(
    request: SendEmailReplyRequest,
    gmail_service: GoogleGmailService = Depends(get_gmail_service),
):
    """
    Replies to an existing email on behalf of the authenticated user.
    Uses `original_message_id` to ensure proper threading.
    """
    try:
        sent_message = await gmail_service.send_email(
            to=request.to,
            subject=request.subject,
            body=request.body,
            cc=request.cc,
            bcc=request.bcc,
            in_reply_to_message_id=request.original_message_id,
        )
        return {
            "message": f"Reply sent successfully. Message ID: {sent_message.get('id')}"
        }
    except HttpError as e:
        error_msg = e.content.decode() if e.content else e
        logger.error(
            "Gmail API error replying to email: {}",
            error_msg,
            exc_info=True,
        )
        raise HTTPException(
            status_code=(
                e.resp.status
                if hasattr(e, "resp")
                else status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=f"Failed to reply to email: {error_msg}",
        )
    except Exception as e:
        logger.error("Unexpected error replying to email: {}", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while replying to email.",
        )


@router.get(
    "/messages/{message_id}",
    response_model=FullEmailDetails,
    summary="Get full details of a specific email message",
)
async def get_email_details(
    message_id: str, gmail_service: GoogleGmailService = Depends(get_gmail_service)
):
    """
    Retrieves the full content and metadata of a specific email message.
    """
    try:
        message_data = await gmail_service.get_message(message_id, format="full")

        headers = {
            header["name"].lower(): header["value"]
            for header in message_data["payload"]["headers"]
        }

        return FullEmailDetails(
            id=message_data["id"],
            threadId=message_data["threadId"],
            from_email=headers.get("from"),
            to_email=headers.get("to"),
            subject=headers.get("subject"),
            date=headers.get("date"),
        )
    except HttpError as e:
        error_msg = e.content.decode() if e.content else e
        logger.error(
            "Gmail API error getting message details: {}",
            error_msg,
            exc_info=True,
        )
        status_code = (
            e.resp.status
            if hasattr(e, "resp")
            else status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        if status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Message with ID '{message_id}' not found.",
            )
        raise HTTPException(
            status_code=status_code,
            detail=f"Failed to retrieve message details: {error_msg}",
        )
    except Exception as e:
        logger.error("Unexpected error getting message details: {}", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving message details.",
        )


@router.get("/messages", response_model=List[EmailInfo], summary="List email messages")
async def list_emails(
    query: Optional[str] = Query(
        None, description="Gmail search query (e.g., 'in:inbox is:unread')"
    ),
    max_results: int = Query(
        10, ge=1, le=100, description="Maximum number of messages to retrieve"
    ),
    gmail_service: GoogleGmailService = Depends(get_gmail_service),
):
    """
    Lists email messages based on a Gmail search query.
    """
    try:
        messages = await gmail_service.list_messages(
            query=query, max_results=max_results
        )
        return [EmailInfo(**msg) for msg in messages]
    except HttpError as e:
        error_msg = e.content.decode() if e.content else e
        logger.error(
            "Gmail API error listing emails: {}",
            error_msg,
            exc_info=True,
        )
        raise HTTPException(
            status_code=(
                e.resp.status
                if hasattr(e, "resp")
                else status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=f"Failed to list emails: {error_msg}",
        )
    except Exception as e:
        logger.error("Unexpected error listing emails: {}", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while listing emails.",
        )


@router.post(
    "/summarize-email",
    response_model=SummarizeEmailResponse,
    summary="Summarize an email using AI",
)
async def summarize_email(
    request: SummarizeEmailRequest,
    gmail_service: GoogleGmailService = Depends(get_gmail_service),
    ai_service: AIService = Depends(get_ai_service),
):
    """
    Retrieves the content of an email and summarizes it using the AI service.
    """
    try:
        email_content = await gmail_service.get_message_content(request.message_id)
        if not email_content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Could not retrieve content for message ID '{request.message_id}' or message has no readable content.",
            )

        summary = await ai_service.summarize_text(email_content)

        return SummarizeEmailResponse(
            message_id=request.message_id,
            summary=summary,
            original_content=email_content,
        )
    except HttpError as e:
        error_msg = e.content.decode() if e.content else e
        logger.error(
            "Gmail API error during summarization: {}",
            error_msg,
            exc_info=True,
        )
        status_code = (
            e.resp.status
            if hasattr(e, "resp")
            else status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        if status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Message with ID '{request.message_id}' not found.",
            )
        raise HTTPException(
            status_code=status_code,
            detail=f"Failed to retrieve email for summarization: {error_msg}",
        )
    except Exception as e:
        logger.error("Unexpected error during email summarization: {}", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during email summarization.",
        )
