"""
Email wrapper service that handles multiple email providers.
Gracefully falls back when services aren't configured.
"""
import logging
from typing import Optional, Dict, Any, List
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from src.core.config import settings

logger = logging.getLogger(__name__)


class EmailWrapper:
    """
    Email service wrapper that supports multiple providers.
    Only uses services that are actually configured.
    """
    
    def __init__(self):
        self._service = None
        self._provider = None
        self._initialize_service()
    
    def _initialize_service(self):
        """Initialize the best available email service."""
        # Try SendGrid first (if configured)
        if settings.EMAIL_PROVIDER == "sendgrid" and settings.SENDGRID_API_KEY:
            try:
                import sendgrid
                self._service = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
                self._provider = "sendgrid"
                logger.info("Email service initialized with SendGrid")
            except ImportError:
                logger.warning("SendGrid library not installed")
            except Exception as e:
                logger.error(f"Failed to initialize SendGrid: {e}")
        
        # Try SMTP as fallback
        if not self._service and settings.SMTP_HOST:
            self._provider = "smtp"
            logger.info("Email service initialized with SMTP")
        
        # No email service available
        if not self._provider:
            logger.warning("No email service configured")
    
    def is_available(self) -> bool:
        """Check if any email service is available."""
        return self._provider is not None
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        plain_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None
    ) -> bool:
        """
        Send an email using the configured service.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email body
            plain_content: Plain text fallback
            from_email: Sender email (uses default if not provided)
            from_name: Sender name (uses default if not provided)
            
        Returns:
            Success status
        """
        if not self.is_available():
            logger.error("Attempted to send email but no service configured")
            return False
        
        from_email = from_email or settings.EMAIL_FROM
        from_name = from_name or settings.EMAIL_FROM_NAME
        
        try:
            if self._provider == "sendgrid":
                return await self._send_sendgrid(
                    to_email, subject, html_content, plain_content,
                    from_email, from_name
                )
            elif self._provider == "smtp":
                return await self._send_smtp(
                    to_email, subject, html_content, plain_content,
                    from_email, from_name
                )
            else:
                return False
                
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    async def send_plain_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None
    ) -> bool:
        """
        Send a plain text email.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Plain text body
            from_email: Sender email
            from_name: Sender name
            
        Returns:
            Success status
        """
        # Convert plain text to basic HTML
        html_body = f"<pre>{body}</pre>"
        
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_body,
            plain_content=body,
            from_email=from_email,
            from_name=from_name
        )
    
    async def _send_sendgrid(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        plain_content: Optional[str],
        from_email: str,
        from_name: str
    ) -> bool:
        """Send email via SendGrid."""
        try:
            from sendgrid.helpers.mail import Mail, Email, To, Content
            
            message = Mail(
                from_email=Email(from_email, from_name),
                to_emails=To(to_email),
                subject=subject
            )
            
            if plain_content:
                message.add_content(Content("text/plain", plain_content))
            message.add_content(Content("text/html", html_content))
            
            response = self._service.send(message)
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"Email sent successfully to {to_email}")
                return True
            else:
                logger.error(f"SendGrid returned status {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"SendGrid error: {e}")
            return False
    
    async def _send_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        plain_content: Optional[str],
        from_email: str,
        from_name: str
    ) -> bool:
        """Send email via SMTP."""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{from_name} <{from_email}>"
            msg['To'] = to_email
            
            # Add content
            if plain_content:
                part1 = MIMEText(plain_content, 'plain')
                msg.attach(part1)
            
            part2 = MIMEText(html_content, 'html')
            msg.attach(part2)
            
            # Send via SMTP
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"SMTP error: {e}")
            return False
    
    async def send_template_email(
        self,
        to_email: str,
        template_id: str,
        template_data: Dict[str, Any],
        from_email: Optional[str] = None,
        from_name: Optional[str] = None
    ) -> bool:
        """
        Send email using a template (SendGrid only).
        Falls back to plain email if templates not available.
        """
        if self._provider != "sendgrid" or not template_id:
            # Fallback to plain email
            subject = template_data.get("subject", "Notification from Nyelux")
            body = self._create_plain_body_from_template_data(template_data)
            return await self.send_plain_email(
                to_email, subject, body, from_email, from_name
            )
        
        # Use SendGrid template
        try:
            from sendgrid.helpers.mail import Mail, Email, To
            
            from_email = from_email or settings.EMAIL_FROM
            from_name = from_name or settings.EMAIL_FROM_NAME
            
            message = Mail(
                from_email=Email(from_email, from_name),
                to_emails=To(to_email)
            )
            message.template_id = template_id
            message.dynamic_template_data = template_data
            
            response = self._service.send(message)
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"Template email sent successfully to {to_email}")
                return True
            else:
                logger.error(f"SendGrid returned status {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Template email error: {e}")
            return False
    
    def _create_plain_body_from_template_data(self, data: Dict[str, Any]) -> str:
        """Create a plain text body from template data."""
        body = data.get("body", "")
        
        if "action_url" in data:
            body += f"\n\nView details: {data['action_url']}"
        
        return body


# Create singleton instance
email_wrapper = EmailWrapper()
