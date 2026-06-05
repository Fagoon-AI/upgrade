import base64
import json
from loguru import logger
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GoogleGmailService:
    def __init__(self, credentials: Credentials):
        """
        Initializes the Gmail API service.
        Args:
            credentials: The google.oauth2.credentials.Credentials object for the authenticated user.
        """
        self.credentials = credentials
        self._service = None

    @property
    def service(self):
        """
        Returns the Gmail API service client, building it if it doesn't exist.
        """
        if self._service is None:
            try:
                self._service = build("gmail", "v1", credentials=self.credentials)
                logger.info("Gmail API service built successfully.")
            except Exception as e:
                logger.error(f"Error building Gmail API service: {e}", exc_info=True)
                raise HttpError(f"Could not build Gmail service: {e}")
        return self._service

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        sender_email: Optional[str] = "me",
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        in_reply_to_message_id: Optional[str] = None,
    ) -> Dict:
        """
        Sends an email.
        Args:
            to (str): Recipient email address.
            subject (str): Subject of the email.
            body (str): HTML or plain text body of the email.
            sender_email (str): The email address to send from (default 'me').
            cc (str): Carbon copy recipients (comma-separated).
            bcc (str): Blind carbon copy recipients (comma-separated).
            in_reply_to_message_id (str): If this is a reply, the original message ID.
        Returns:
            Dict: The response from the Gmail API after sending the message.
        Raises:
            HttpError: If the Gmail API call fails.
        """
        message = MIMEMultipart()
        message["to"] = to
        if cc:
            message["cc"] = cc
        if bcc:
            message["bcc"] = bcc
        message["from"] = (
            sender_email
        )
        message["subject"] = subject

        if in_reply_to_message_id:
            message["In-Reply-To"] = in_reply_to_message_id
            message["References"] = (
                in_reply_to_message_id
            )

        msg = MIMEText(body, "html")
        message.attach(msg)

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        body = {"raw": raw_message}

        try:
            sent_message = (
                self.service.users()
                .messages()
                .send(userId=sender_email, body=body)
                .execute()
            )
            logger.info(
                f"Email sent successfully to {to}, Message ID: {sent_message.get('id')}"
            )
            return sent_message
        except HttpError as error:
            logger.error(f"Failed to send email: {error}", exc_info=True)
            raise

    async def get_message(self, message_id: str, format: str = "full") -> Dict:
        """
        Retrieves a single email message by its ID.
        Args:
            message_id (str): The ID of the message to retrieve.
            format (str): The format of the message data. Can be "full", "metadata", "raw", or "minimal".
        Returns:
            Dict: The message data.
        Raises:
            HttpError: If the Gmail API call fails.
        """
        logger.info(f"Retrieved message with ID: {message_id}")
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format=format)
                .execute()
            )
            logger.info(f"Retrieved message with ID: {message_id}")
            return message
        except HttpError as error:
            logger.error(
                f"Failed to retrieve message {message_id}: {error}", exc_info=True
            )
            raise

    async def list_messages(
        self, query: Optional[str] = None, max_results: int = 10
    ) -> List[Dict]:
        """
        Lists email messages for the authenticated user.
        Args:
            query (str): Gmail search query string.
            max_results (int): Maximum number of messages to return.
        Returns:
            List[Dict]: A list of message IDs and thread IDs.
        Raises:
            HttpError: If the Gmail API call fails.
            ValueError: If the API response is malformed.
        """
        try:
            messages_list = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )
            
            # Improved logging
            logger.debug(f"Gmail API response: {json.dumps(messages_list, indent=2)}")
            
            # More robust handling of response
            if not isinstance(messages_list, dict):
                raise ValueError(f"Unexpected API response format: {type(messages_list)}")
                
            messages = messages_list.get("messages", [])
            
            if not isinstance(messages, list):
                raise ValueError(f"'messages' field is not a list: {type(messages)}")
                
            logger.info(f"Listed {len(messages)} messages with query '{query}'.")
            return messages
            
        except HttpError as error:
            logger.error(
                f"Failed to list messages with query '{query}': {error}", 
                exc_info=True
            )
            raise
        except (ValueError, KeyError) as error:
            logger.error(
                f"Unexpected error processing API response: {error}\n"
                f"Full response: {messages_list}",
                exc_info=True
            )
            raise ValueError("Failed to process Gmail API response") from error

    # async def list_messages(
    #     self, query: Optional[str] = None, max_results: int = 10
    # ) -> List[Dict]:
    #     """
    #     Lists email messages for the authenticated user.
    #     Args:
    #         query (str): Gmail search query string (e.g., "from:someone@example.com subject:test").
    #         max_results (int): Maximum number of messages to return.
    #     Returns:
    #         List[Dict]: A list of message IDs and thread IDs.
    #     Raises:
    #         HttpError: If the Gmail API call fails.
    #     """
    #     try:
    #         messages_list = (
    #             self.service.users()
    #             .messages()
    #             .list(userId="me", q=query, maxResults=max_results)
    #             .execute()
    #         )
    #         logger.debug(f"================== DATA IS: {messages_list}")
    #         messages = messages_list.get("messages", [])
    #         logger.info(f"Listed {len(messages)} messages with query '{query}'.")
    #         return messages
    #     except HttpError as error:
    #         logger.error(
    #             f"Failed to list messages with query '{query}': {error}", exc_info=True
    #         )
    #         raise

    async def get_message_content(self, message_id: str) -> Optional[str]:
        """
        Extracts the plain text or HTML content from a Gmail message.
        This function iterates through message parts to find the most suitable content.
        """
        message = await self.get_message(message_id, format="full")
        payload = message.get("payload")

        if not payload:
            return None

        parts = payload.get("parts", [])
        for part in parts:
            if part.get("mimeType") == "text/html":
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
            elif part.get("mimeType") == "text/plain":
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")

        if payload.get("body") and payload["body"].get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

        return None
