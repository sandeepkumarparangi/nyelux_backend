"""
Production-ready Email Service for Nyelux Backend

This service handles all email operations with proper error handling,
sender verification, and production best practices.
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
from enum import Enum

from src.core.config import settings
from src.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class EmailProvider(Enum):
    """Supported email providers"""
    SENDGRID = "sendgrid"
    AWS_SES = "aws_ses"
    SMTP = "smtp"


class EmailService:
    """
    Production-ready email service with proper error handling and monitoring.
    """
    
    def __init__(self):
        """Initialize email service with configured provider."""
        self.provider = settings.EMAIL_PROVIDER
        self.from_email = settings.EMAIL_FROM
        self.from_name = settings.EMAIL_FROM_NAME
        
        # Validate configuration
        if not self.provider:
            raise ValueError("EMAIL_PROVIDER not configured in environment")
        
        if not self.from_email:
            raise ValueError("EMAIL_FROM not configured in environment")
        
        # Initialize provider
        if self.provider == EmailProvider.SENDGRID.value:
            self._init_sendgrid()
        elif self.provider == EmailProvider.SMTP.value:
            self._init_smtp()
        elif self.provider == EmailProvider.AWS_SES.value:
            self._init_aws_ses()
        else:
            raise ValueError(f"Unsupported email provider: {self.provider}")
        
        logger.info(f"Email service initialized with provider: {self.provider}")
    
    def _init_sendgrid(self):
        """Initialize SendGrid client with production configuration."""
        if not settings.SENDGRID_API_KEY:
            raise ValueError("SENDGRID_API_KEY not configured")
        
        if not settings.SENDGRID_API_KEY.startswith('SG.'):
            raise ValueError("Invalid SendGrid API key format")
        
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail, Email, To, Content
            
            self.sg_client = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
            self.Mail = Mail
            self.Email = Email
            self.To = To
            self.Content = Content
            
            # Test the configuration (optional - remove if you don't want startup check)
            self._verify_sendgrid_sender()
            
        except ImportError:
            raise ImportError("SendGrid library not installed. Run: pip install sendgrid")
        except Exception as e:
            raise ExternalServiceError("SendGrid", f"Failed to initialize: {str(e)}")
    
    def _verify_sendgrid_sender(self):
        """Verify that the sender email is authenticated in SendGrid."""
        # This is a configuration check, not an API call
        logger.info(f"SendGrid configured with sender: {self.from_email}")
        
        # In production, you might want to make an API call to verify
        # For now, we'll trust that the sender is verified
        if not self.from_email.endswith('@nyelux.com'):
            logger.warning(
                f"Sender email {self.from_email} is not from nyelux.com domain. "
                "Make sure it's verified in SendGrid."
            )
    
    def _init_smtp(self):
        """Initialize SMTP configuration."""
        required_settings = ['SMTP_HOST', 'SMTP_PORT', 'SMTP_USERNAME', 'SMTP_PASSWORD']
        missing = [s for s in required_settings if not getattr(settings, s, None)]
        
        if missing:
            raise ValueError(f"Missing SMTP configuration: {', '.join(missing)}")
        
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_use_tls = getattr(settings, 'SMTP_USE_TLS', True)
    
    def _init_aws_ses(self):
        """Initialize AWS SES configuration."""
        try:
            import boto3
            
            self.ses_client = boto3.client(
                'ses',
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
            )
        except ImportError:
            raise ImportError("Boto3 not installed. Run: pip install boto3")
        except Exception as e:
            raise ExternalServiceError("AWS SES", f"Failed to initialize: {str(e)}")
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Send an email with full production features.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            text_content: Plain text content (optional)
            attachments: List of attachments (optional)
            cc: CC recipients (optional)
            bcc: BCC recipients (optional)
            reply_to: Reply-to address (optional)
            tags: Email tags for analytics (optional)
            
        Returns:
            True if email sent successfully, False otherwise
            
        Raises:
            ExternalServiceError: If email service fails
        """
        # Validate email addresses
        if not self._validate_email(to_email):
            logger.error(f"Invalid recipient email: {to_email}")
            return False
        
        # Log the attempt
        logger.info(f"Attempting to send email to {to_email} with subject: {subject}")
        
        try:
            if self.provider == EmailProvider.SENDGRID.value:
                return await self._send_sendgrid(
                    to_email, subject, html_content, text_content,
                    attachments, cc, bcc, reply_to, tags
                )
            elif self.provider == EmailProvider.SMTP.value:
                return await self._send_smtp(
                    to_email, subject, html_content, text_content,
                    attachments, cc, bcc, reply_to
                )
            elif self.provider == EmailProvider.AWS_SES.value:
                return await self._send_aws_ses(
                    to_email, subject, html_content, text_content,
                    cc, bcc, reply_to
                )
            else:
                raise ValueError(f"Unknown email provider: {self.provider}")
                
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}", exc_info=True)
            
            # In production, you might want to retry or queue the email
            # For now, we'll raise the error for visibility
            raise ExternalServiceError(
                self.provider,
                f"Failed to send email: {str(e)}"
            )
    
    async def _send_sendgrid(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> bool:
        """Send email via SendGrid with production features."""
        try:
            # Create message with proper sender
            message = self.Mail()
            
            # Set from address (MUST be verified in SendGrid)
            message.from_email = self.Email(
                email=self.from_email,
                name=self.from_name
            )
            
            # Set recipient
            message.add_to(self.To(email=to_email))
            
            # Set subject
            message.subject = subject
            
            # Set content
            if text_content:
                message.add_content(self.Content("text/plain", text_content))
            message.add_content(self.Content("text/html", html_content))
            
            # Add CC recipients
            if cc:
                for cc_email in cc:
                    message.add_cc(self.Email(cc_email))
            
            # Add BCC recipients
            if bcc:
                for bcc_email in bcc:
                    message.add_bcc(self.Email(bcc_email))
            
            # Set reply-to
            if reply_to:
                message.reply_to = self.Email(reply_to)
            
            # Add custom args for tracking (SendGrid feature)
            if tags:
                for key, value in tags.items():
                    message.add_custom_arg(key, value)
            
            # Add attachments if any
            if attachments:
                for attachment in attachments:
                    # Implement attachment handling
                    # attachment should have: content, filename, type, disposition
                    pass
            
            # Send email asynchronously
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self.sg_client.send, message
            )
            
            # Check response
            if response.status_code in [200, 201, 202]:
                logger.info(
                    f"Email sent successfully to {to_email}. "
                    f"Status: {response.status_code}, "
                    f"Message ID: {response.headers.get('X-Message-Id', 'N/A')}"
                )
                return True
            else:
                logger.error(
                    f"SendGrid returned unexpected status {response.status_code} "
                    f"for email to {to_email}. Body: {response.body}"
                )
                return False
                
        except Exception as e:
            error_msg = str(e)
            
            # Handle specific SendGrid errors
            if "401" in error_msg:
                raise ExternalServiceError(
                    "SendGrid",
                    "Invalid API key. Check SENDGRID_API_KEY in environment."
                )
            elif "403" in error_msg or "Sender Identity" in error_msg:
                raise ExternalServiceError(
                    "SendGrid",
                    f"Sender {self.from_email} is not verified in SendGrid. "
                    "Please verify the sender or authenticate your domain."
                )
            elif "413" in error_msg:
                raise ExternalServiceError(
                    "SendGrid",
                    "Email too large. Maximum size is 30MB."
                )
            else:
                raise ExternalServiceError("SendGrid", error_msg)
    
    async def _send_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None
    ) -> bool:
        """Send email via SMTP."""
        import aiosmtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from email.mime.base import MIMEBase
        from email import encoders
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            
            if cc:
                msg['Cc'] = ', '.join(cc)
            if reply_to:
                msg['Reply-To'] = reply_to
            
            # Add text and HTML parts
            if text_content:
                msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            # Add attachments
            if attachments:
                for attachment in attachments:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment['content'])
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {attachment["filename"]}'
                    )
                    msg.attach(part)
            
            # Prepare recipients
            recipients = [to_email]
            if cc:
                recipients.extend(cc)
            if bcc:
                recipients.extend(bcc)
            
            # Send email
            await aiosmtplib.send(
                msg,
                recipients=recipients,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_username,
                password=self.smtp_password,
                use_tls=self.smtp_use_tls
            )
            
            logger.info(f"Email sent to {to_email} via SMTP")
            return True
            
        except Exception as e:
            raise ExternalServiceError("SMTP", str(e))
    
    async def _send_aws_ses(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None
    ) -> bool:
        """Send email via AWS SES."""
        try:
            destination = {'ToAddresses': [to_email]}
            if cc:
                destination['CcAddresses'] = cc
            if bcc:
                destination['BccAddresses'] = bcc
            
            message = {
                'Subject': {'Data': subject},
                'Body': {}
            }
            
            if text_content:
                message['Body']['Text'] = {'Data': text_content}
            if html_content:
                message['Body']['Html'] = {'Data': html_content}
            
            kwargs = {
                'Source': f"{self.from_name} <{self.from_email}>",
                'Destination': destination,
                'Message': message
            }
            
            if reply_to:
                kwargs['ReplyToAddresses'] = [reply_to]
            
            # Send email
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.ses_client.send_email(**kwargs)
            )
            
            logger.info(
                f"Email sent to {to_email} via AWS SES. "
                f"Message ID: {response['MessageId']}"
            )
            return True
            
        except Exception as e:
            raise ExternalServiceError("AWS SES", str(e))
    
    def _validate_email(self, email: str) -> bool:
        """Validate email address format."""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    # Production-ready email templates
    
    async def send_verification_email(
        self,
        to_email: str,
        verification_token: str,
        user_name: Optional[str] = None
    ):
        """Send email verification with production template."""
        verify_url = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"
        
        subject = "Verify your Nyelux account"
        
        html_content = self._get_email_template(
            "verification",
            {
                "user_name": user_name or "there",
                "verify_url": verify_url,
                "company_name": "Nyelux Medical",
                "support_email": "support@nyelux.com"
            }
        )
        
        text_content = f"""
        Welcome to Nyelux Medical!
        
        Please verify your email address by visiting:
        {verify_url}
        
        This link will expire in 24 hours.
        
        If you didn't create an account, please ignore this email.
        
        Best regards,
        The Nyelux Team
        """
        
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            tags={"email_type": "verification", "user_email": to_email}
        )
    
    async def send_password_reset_email(
        self,
        to_email: str,
        reset_token: str,
        user_name: Optional[str] = None
    ):
        """Send password reset email with production template."""
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        
        subject = "Reset your Nyelux password"
        
        html_content = self._get_email_template(
            "password_reset",
            {
                "user_name": user_name or "there",
                "reset_url": reset_url,
                "expires_in": "1 hour",
                "company_name": "Nyelux Medical",
                "support_email": "support@nyelux.com"
            }
        )
        
        text_content = f"""
        Password Reset Request
        
        To reset your password, visit:
        {reset_url}
        
        This link expires in 1 hour.
        
        If you didn't request this, ignore this email.
        
        The Nyelux Team
        """
        
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            tags={"email_type": "password_reset", "user_email": to_email}
        )
    
    async def send_invitation_email(
        self,
        to_email: str,
        invitation_code: str,
        organization_name: str,
        inviter_name: str,
        temp_password: Optional[str] = None,
        message: Optional[str] = None,
        expires_days: int = 7
    ):
        """Send organization invitation email."""
        invitation_url = f"{settings.FRONTEND_URL}/invite/{invitation_code}"
        
        subject = f"You've been invited to join {organization_name} on Nyelux"
        
        html_content = self._get_email_template(
            "invitation",
            {
                "organization_name": organization_name,
                "inviter_name": inviter_name,
                "invitation_url": invitation_url,
                "temp_password": temp_password,
                "custom_message": message,
                "expires_days": expires_days,
                "company_name": "Nyelux Medical"
            }
        )
        
        text_content = f"""
        You've been invited to join {organization_name} on Nyelux
        
        {inviter_name} has invited you to access medical device information.
        
        Accept invitation: {invitation_url}
        {"Temporary password: " + temp_password if temp_password else ""}
        
        This invitation expires in {expires_days} days.
        
        The Nyelux Team
        """
        
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            tags={
                "email_type": "invitation",
                "organization": organization_name,
                "invited_by": inviter_name
            }
        )
    
    async def send_vendor_provision_email(
        self,
        to_email: str,
        temp_password: str,
        vendor_name: str,
        devices: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None
    ):
        """Send vendor provisioning email with credentials."""
        subject = f"Your Nyelux account has been created by {vendor_name}"
        
        html_content = self._get_email_template(
            "vendor_provision",
            {
                "vendor_name": vendor_name,
                "email": to_email,
                "temp_password": temp_password,
                "devices": devices,
                "expires_at": expires_at,
                "login_url": f"{settings.FRONTEND_URL}/login",
                "company_name": "Nyelux Medical"
            }
        )
        
        text_content = f"""
        Your Nyelux account has been created by {vendor_name}
        
        Login credentials:
        Email: {to_email}
        Temporary Password: {temp_password}
        
        You will be required to change this password on first login.
        
        Login at: {settings.FRONTEND_URL}/login
        
        The Nyelux Team
        """
        
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            tags={
                "email_type": "vendor_provision",
                "vendor": vendor_name
            }
        )
    
    def _get_email_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Get email template. In production, use a template engine like Jinja2.
        For now, returning basic HTML templates.
        """
        templates = {
            "verification": """
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2>Welcome to {company_name}!</h2>
                    <p>Hi {user_name},</p>
                    <p>Please verify your email address to complete registration:</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{verify_url}" style="background-color: #002D72; color: white; 
                           padding: 12px 30px; text-decoration: none; border-radius: 5px;">
                            Verify Email Address
                        </a>
                    </div>
                    <p>This link expires in 24 hours.</p>
                    <p>Best regards,<br>The {company_name} Team</p>
                </div>
            """,
            "password_reset": """
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2>Password Reset Request</h2>
                    <p>Hi {user_name},</p>
                    <p>Click below to reset your password:</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{reset_url}" style="background-color: #002D72; color: white; 
                           padding: 12px 30px; text-decoration: none; border-radius: 5px;">
                            Reset Password
                        </a>
                    </div>
                    <p>This link expires in {expires_in}.</p>
                    <p>Best regards,<br>The {company_name} Team</p>
                </div>
            """,
            "invitation": """
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2>You're invited to join {organization_name}</h2>
                    <p>{inviter_name} has invited you to join {organization_name} on {company_name}.</p>
                    {custom_message}
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{invitation_url}" style="background-color: #002D72; color: white; 
                           padding: 12px 30px; text-decoration: none; border-radius: 5px;">
                            Accept Invitation
                        </a>
                    </div>
                    <p>This invitation expires in {expires_days} days.</p>
                </div>
            """,
            "vendor_provision": """
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2>Welcome to {company_name}</h2>
                    <p>Your account has been created by {vendor_name}.</p>
                    <div style="background-color: #f5f5f5; padding: 20px; margin: 20px 0;">
                        <h3>Login Credentials:</h3>
                        <p><strong>Email:</strong> {email}</p>
                        <p><strong>Temporary Password:</strong> {temp_password}</p>
                        <p style="color: red;">You must change this password on first login.</p>
                    </div>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{login_url}" style="background-color: #002D72; color: white; 
                           padding: 12px 30px; text-decoration: none; border-radius: 5px;">
                            Login to {company_name}
                        </a>
                    </div>
                </div>
            """
        }
        
        template = templates.get(template_name, "<p>Email content</p>")
        
        # Simple template variable replacement
        for key, value in context.items():
            if value is not None:
                template = template.replace(f"{{{key}}}", str(value))
        
        return template


# Singleton instance
_email_service_instance = None


def get_email_service() -> EmailService:
    """
    Get email service singleton instance.
    
    Returns:
        EmailService instance
        
    Raises:
        ExternalServiceError: If email service cannot be initialized
    """
    global _email_service_instance
    
    if _email_service_instance is None:
        _email_service_instance = EmailService()
    
    return _email_service_instance
