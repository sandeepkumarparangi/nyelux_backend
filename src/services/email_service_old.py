"""
Email service for sending transactional emails.

Provides email sending functionality with support for multiple providers
and proper error handling.
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio

from src.core.config import settings
from src.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class EmailService:
    """
    Service for sending emails via configured email provider.
    Supports SendGrid, AWS SES, or SMTP.
    """
    
    def __init__(self):
        """Initialize email service with configured provider."""
        self.provider = settings.EMAIL_PROVIDER
        self.from_email = settings.EMAIL_FROM
        self.from_name = settings.EMAIL_FROM_NAME
        
        if not self.provider:
            logger.warning("Email provider not configured")
            
        # Initialize provider client
        if self.provider == "sendgrid":
            self._init_sendgrid()
        elif self.provider == "smtp":
            self._init_smtp()
        else:
            logger.warning(f"Unknown email provider: {self.provider}")
    
    def _init_sendgrid(self):
        """Initialize SendGrid client."""
        if not settings.SENDGRID_API_KEY:
            raise ExternalServiceError(
                "SendGrid",
                "SendGrid API key not configured"
            )
        
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail
            import ssl
            import certifi
            import urllib3
            
            # Disable SSL warnings for development (remove in production)
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            self.sg_client = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
            self.Mail = Mail
        except ImportError:
            raise ExternalServiceError(
                "SendGrid",
                "SendGrid library not installed. Run: pip install sendgrid"
            )
    
    def _init_smtp(self):
        """Initialize SMTP configuration."""
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_use_tls = settings.SMTP_USE_TLS
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Send an email to a single recipient.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            text_content: Plain text content (optional)
            attachments: List of attachments (optional)
            
        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.provider:
            logger.warning(f"Email not sent to {to_email}: No provider configured")
            return False
        
        try:
            if self.provider == "sendgrid":
                return await self._send_sendgrid(
                    to_email, subject, html_content, text_content, attachments
                )
            elif self.provider == "smtp":
                return await self._send_smtp(
                    to_email, subject, html_content, text_content, attachments
                )
            else:
                logger.error(f"Unknown email provider: {self.provider}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    async def _send_sendgrid(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Send email via SendGrid."""
        try:
            message = self.Mail(
                from_email=(self.from_email, self.from_name),
                to_emails=to_email,
                subject=subject,
                html_content=html_content
            )
            
            if text_content:
                message.plain_text_content = text_content
            
            # Add attachments if any
            if attachments:
                for attachment in attachments:
                    # attachment should have: content, filename, type
                    pass  # Implement attachment handling
            
            # Send in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self.sg_client.send, message
            )
            
            logger.info(f"Email sent to {to_email} via SendGrid: {response.status_code}")
            return response.status_code in [200, 201, 202]
            
        except Exception as e:
            logger.error(f"SendGrid error: {e}")
            return False
    
    async def _send_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Send email via SMTP."""
        import aiosmtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            
            # Add text and HTML parts
            if text_content:
                msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            # Send email
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_username,
                password=self.smtp_password,
                use_tls=self.smtp_use_tls
            )
            
            logger.info(f"Email sent to {to_email} via SMTP")
            return True
            
        except Exception as e:
            logger.error(f"SMTP error: {e}")
            return False
    
    async def send_verification_email(
        self,
        to_email: str,
        verification_token: str,
        user_name: Optional[str] = None
    ):
        """
        Send email verification link to new user.
        
        Args:
            to_email: User's email address
            verification_token: Verification token
            user_name: User's first name (optional)
        """
        verify_url = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"
        
        subject = "Verify your Nyelux account"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c5282;">Welcome to Nyelux Medical!</h2>
                
                <p>Hi {user_name or 'there'},</p>
                
                <p>Thank you for creating an account with Nyelux Medical Device Intelligence Platform.</p>
                
                <p>To complete your registration and access our comprehensive medical device database, 
                please verify your email address by clicking the button below:</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verify_url}" 
                       style="background-color: #3182ce; color: white; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; display: inline-block;">
                        Verify Email Address
                    </a>
                </div>
                
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #3182ce;">{verify_url}</p>
                
                <p>This link will expire in 24 hours for security purposes.</p>
                
                <p>If you didn't create an account with Nyelux, please ignore this email.</p>
                
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
                
                <p style="color: #718096; font-size: 14px;">
                    Best regards,<br>
                    The Nyelux Team
                </p>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Welcome to Nyelux Medical!
        
        Hi {user_name or 'there'},
        
        Thank you for creating an account with Nyelux Medical Device Intelligence Platform.
        
        To complete your registration, please verify your email address by visiting:
        {verify_url}
        
        This link will expire in 24 hours.
        
        If you didn't create an account with Nyelux, please ignore this email.
        
        Best regards,
        The Nyelux Team
        """
        
        await self.send_email(to_email, subject, html_content, text_content)
    
    async def send_password_reset_email(
        self,
        to_email: str,
        reset_token: str,
        user_name: Optional[str] = None
    ):
        """
        Send password reset email.
        
        Args:
            to_email: User's email address
            reset_token: Password reset token
            user_name: User's first name (optional)
        """
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        
        subject = "Reset your Nyelux password"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c5282;">Password Reset Request</h2>
                
                <p>Hi {user_name or 'there'},</p>
                
                <p>We received a request to reset your password for your Nyelux account.</p>
                
                <p>To reset your password, click the button below:</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" 
                       style="background-color: #3182ce; color: white; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; display: inline-block;">
                        Reset Password
                    </a>
                </div>
                
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #3182ce;">{reset_url}</p>
                
                <p>This link will expire in 1 hour for security purposes.</p>
                
                <p>If you didn't request a password reset, please ignore this email. 
                Your password will remain unchanged.</p>
                
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
                
                <p style="color: #718096; font-size: 14px;">
                    Best regards,<br>
                    The Nyelux Team
                </p>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Password Reset Request
        
        Hi {user_name or 'there'},
        
        We received a request to reset your password for your Nyelux account.
        
        To reset your password, visit:
        {reset_url}
        
        This link will expire in 1 hour.
        
        If you didn't request a password reset, please ignore this email.
        
        Best regards,
        The Nyelux Team
        """
        
        await self.send_email(to_email, subject, html_content, text_content)
    
    def _render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Render email template with context.
        In production, this would use a proper template engine.
        """
        # For now, return empty string
        # In production, implement Jinja2 or similar
        return ""


# Dependency function for FastAPI
def get_email_service() -> EmailService:
    """
    Get email service instance for dependency injection.
    
    Returns:
        EmailService instance
    """
    return EmailService()
