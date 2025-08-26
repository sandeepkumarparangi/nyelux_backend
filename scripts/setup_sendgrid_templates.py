#!/usr/bin/env python
"""
Setup SendGrid email templates for Nyelux.
Creates or updates email templates in SendGrid.
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.email_service import email_service
from src.core.config import settings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import *
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Template definitions
TEMPLATES = {
    "device_recall": {
        "name": "Device Recall Notification",
        "subject": "URGENT: Medical Device Recall - {{device_name}}",
        "html_content": """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; }
        .urgent { background: #dc3545; color: white; padding: 10px; }
        .device-info { background: #f8f9fa; padding: 15px; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="urgent">
        <h1>URGENT: Medical Device Recall</h1>
    </div>
    <p>Dear {{user_name}},</p>
    <p>A medical device you may be using has been recalled by the manufacturer.</p>
    <div class="device-info">
        <h3>Device Information:</h3>
        <ul>
            <li><strong>Device:</strong> {{device_name}}</li>
            <li><strong>Manufacturer:</strong> {{manufacturer_name}}</li>
            <li><strong>Model:</strong> {{model_number}}</li>
            <li><strong>Recall Date:</strong> {{recall_date}}</li>
            <li><strong>Recall Reason:</strong> {{recall_reason}}</li>
        </ul>
    </div>
    <p><strong>Action Required:</strong> {{action_required}}</p>
    <p>For more information, please contact your healthcare provider or visit the FDA website.</p>
    <p>Best regards,<br>Nyelux Medical Safety Team</p>
</body>
</html>
        """
    },
    "device_update": {
        "name": "Device Update Notification",
        "subject": "Update Available: {{device_name}}",
        "html_content": """
<!DOCTYPE html>
<html>
<body>
    <h2>Device Update Available</h2>
    <p>Hi {{user_name}},</p>
    <p>An update is available for your medical device:</p>
    <ul>
        <li><strong>Device:</strong> {{device_name}}</li>
        <li><strong>Update Type:</strong> {{update_type}}</li>
        <li><strong>Version:</strong> {{version}}</li>
    </ul>
    <p>{{update_description}}</p>
    <p><a href="{{update_link}}" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none;">View Update Details</a></p>
</body>
</html>
        """
    },
    "meeting_reminder": {
        "name": "Meeting Reminder",
        "subject": "Reminder: {{meeting_title}} - {{meeting_time}}",
        "html_content": """
<!DOCTYPE html>
<html>
<body>
    <h2>Meeting Reminder</h2>
    <p>Hi {{user_name}},</p>
    <p>This is a reminder about your upcoming meeting:</p>
    <ul>
        <li><strong>Title:</strong> {{meeting_title}}</li>
        <li><strong>Time:</strong> {{meeting_time}}</li>
        <li><strong>Duration:</strong> {{meeting_duration}}</li>
        <li><strong>Host:</strong> {{host_name}}</li>
    </ul>
    <p><a href="{{meeting_link}}" style="background: #28a745; color: white; padding: 10px 20px; text-decoration: none;">Join Meeting</a></p>
</body>
</html>
        """
    }
}


async def create_templates():
    """Create email templates in SendGrid"""
    if not settings.SENDGRID_API_KEY:
        logger.error("SENDGRID_API_KEY not configured")
        return False
    
    client = SendGridAPIClient(settings.SENDGRID_API_KEY)
    created = 0
    
    for template_key, template_data in TEMPLATES.items():
        try:
            # Create template
            response = client.marketing.templates.post(
                request_body={
                    "name": template_data["name"],
                    "generation": "dynamic"
                }
            )
            
            template_id = response.to_dict["id"]
            logger.info(f"Created template: {template_data['name']} (ID: {template_id})")
            
            # Create template version
            version_response = client.marketing.templates.versions.post(
                template_id=template_id,
                request_body={
                    "active": 1,
                    "name": "Version 1",
                    "html_content": template_data["html_content"],
                    "plain_content": "Please view this email in HTML format",
                    "generate_plain_content": True,
                    "subject": template_data["subject"]
                }
            )
            
            logger.info(f"Created template version for: {template_data['name']}")
            created += 1
            
            # Store template ID in environment (you would update .env manually)
            logger.info(f"Add to .env: SENDGRID_{template_key.upper()}_TEMPLATE_ID={template_id}")
            
        except Exception as e:
            logger.error(f"Failed to create template {template_key}: {e}")
    
    return created > 0


async def main():
    """Setup SendGrid templates"""
    try:
        logger.info("Setting up SendGrid templates...")
        
        if not settings.SENDGRID_API_KEY:
            logger.error("SENDGRID_API_KEY not configured in environment")
            return 1
        
        success = await create_templates()
        
        if success:
            logger.info("SendGrid templates created successfully!")
            logger.info("IMPORTANT: Update your .env file with the template IDs printed above")
            return 0
        else:
            logger.error("Failed to create templates")
            return 1
        
    except Exception as e:
        logger.error(f"Failed to setup templates: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
