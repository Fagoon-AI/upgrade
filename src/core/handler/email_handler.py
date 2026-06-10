import aiosmtplib
from loguru import logger

from src.core.settings import system_setting
from src.utils.upgrade_auth.app_error import AppError


class SMTPHandler:
    """
    Handles SMTP client connections and operations.
    """

    def __init__(self):
        self._client: aiosmtplib.SMTP | None = None

    @property
    async def connect_client(self) -> aiosmtplib.SMTP:
        """
        Connects and logs into the SMTP server if not already connected.
        Returns the connected SMTP client.
        """
        if self._client and self._client.is_connected:
            return self._client

        try:
            logger.info(
                "Attempting to connect to {}:{} with user {}",
                system_setting.EMAIL_HOST,
                system_setting.EMAIL_PORT,
                system_setting.EMAIL_USERNAME,
            )
            self._client = aiosmtplib.SMTP(
                hostname=system_setting.EMAIL_HOST,
                port=system_setting.EMAIL_PORT,
                use_tls=False,
            )
            await self._client.connect()
            await self._client.login(
                system_setting.EMAIL_USERNAME, system_setting.EMAIL_PASSWORD
            )
            logger.info("Successfully connected and logged into SMTP server.")
            return self._client
        except aiosmtplib.SMTPAuthenticationError as e:
            logger.error("SMTP Authentication Error: {}", e)
            raise AppError(
                f"Authentication failed for email server: {e}", 500
            )
        except aiosmtplib.SMTPConnectError as e:
            logger.error("SMTP Connection Error: {}", e)
            raise AppError(f"Failed to connect to email server: {e}", 500)
        except Exception as e:
            logger.exception(
                "An unexpected error occurred during SMTP connection: {}", e
            )
            raise AppError(
                f"An unexpected error occurred while connecting to email "
                f"server: {e}",
                500,
            )

    async def disconnect_client(self):
        """
        Disconnects the SMTP client if it's connected.
        """
        if self._client and self._client.is_connected:
            try:
                await self._client.quit()
                logger.info("Disconnected from SMTP server.")
            except Exception as e:
                logger.warning(
                    "Error disconnecting from SMTP server: {}", e
                )
            finally:
                self._client = None

    async def send_message(self, message):
        """
        Sends an email message using the connected SMTP client.
        """
        client = await self.connect_client
        try:
            await client.send_message(message)
        except Exception as e:
            logger.error("Error sending email message: {}", e)
            raise AppError(
                f"Failed to send email message: {e}", 500
            )