import aiosmtplib
from email.mime.text import MIMEText
from email.header import Header
from loguru import logger

from src.core.settings import system_setting
from src.utils.upgrade_auth.app_error import AppError

async def send_mail(to_email: str, url: str, email_type: str):
    """
    Sends an email based on the specified type (signup or forgot_password).
    """
    subject = ""
    html_content = ""

    if email_type == "signup":
        subject = "Welcome to Fagoon! Please verify your email."
        html_content = f"""
        <h1>Welcome to Fagoon AI!</h1>
        <p>Thank you for signing up. Please verify your email by clicking the link below:</p>
        <p><a href="{url}">Verify Your Email</a></p>
        <p>If you did not sign up for this service, please ignore this email.</p>
        """
    elif email_type == "forgot_password":
        subject = "Fagoon's AI Password Reset Request"
        html_content = f"""
        <h1>Password Reset</h1>
        <p>You have requested a password reset. Please click the link below to reset your password:</p>
        <p><a href="{url}">Reset Your Password</a></p>
        <p>This link is valid for 10 minutes.</p>
        <p>If you did not request a password reset, please ignore this email.</p>
        """
    else:
        logger.error(f"Invalid email type: {email_type}")
        raise AppError("Invalid email type specified for sending.", 500)

    msg = MIMEText(html_content, 'html', 'utf-8')
    msg['From'] = Header(system_setting.EMAIL_FROM, 'utf-8')
    msg['To'] = Header(to_email, 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')

    try:
        logger.info(f"Attempting to connect to {system_setting.EMAIL_HOST}:{system_setting.EMAIL_PORT} with user {system_setting.EMAIL_USERNAME}")
        client = aiosmtplib.SMTP(hostname=system_setting.EMAIL_HOST, port=system_setting.EMAIL_PORT, use_tls=False)
        await client.connect()
        await client.login(system_setting.EMAIL_USERNAME, system_setting.EMAIL_PASSWORD)
        await client.send_message(msg)
        await client.quit()
        logger.success(f"Email sent successfully to {to_email}")
        return True
    except aiosmtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP Authentication Error for {to_email}: {e}")
        raise AppError(f"Authentication failed for email server: {e}", 500)
    except aiosmtplib.SMTPConnectError as e:
        logger.error(f"SMTP Connection Error for {to_email}: {e}")
        raise AppError(f"Failed to connect to email server: {e}", 500)
    except Exception as e:
        logger.exception(f"General Error sending email to {to_email}: {e}")
        raise AppError(f"An unexpected error occurred while sending email: {e}", 500)
