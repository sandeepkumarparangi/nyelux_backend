"""
AWS S3 Service for file storage
REAL implementation with proper error handling
"""
import os
import boto3
from botocore.exceptions import ClientError
import mimetypes
from typing import Optional, Dict, Any
import logging
from datetime import datetime, timedelta

from src.core.config import settings

logger = logging.getLogger(__name__)


class S3Service:
    """
    REAL S3 service for file storage.
    Handles uploads, downloads, and presigned URLs.
    """
    
    def __init__(self):
        self.s3_client = None
        self.bucket_name = settings.S3_BUCKET_NAME
        self.cdn_url = settings.CLOUDFRONT_URL
        
        # Only initialize if S3 is configured
        if settings.has_s3_configured():
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
        else:
            logger.warning("S3 not configured. File uploads will not work.")
    
    async def upload_file(
        self,
        file_path: str,
        s3_key: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Upload file to S3.
        Returns the CDN URL of the uploaded file.
        """
        if not self.s3_client:
            raise ValueError("S3 not configured")
            
        try:
            # Detect content type
            content_type, _ = mimetypes.guess_type(file_path)
            if not content_type:
                content_type = 'application/octet-stream'
            
            # Prepare upload parameters
            extra_args = {
                'ContentType': content_type,
                'CacheControl': 'max-age=31536000'  # 1 year cache
            }
            
            if metadata:
                extra_args['Metadata'] = metadata
            
            # Upload file
            self.s3_client.upload_file(
                file_path,
                self.bucket_name,
                s3_key,
                ExtraArgs=extra_args
            )
            
            logger.info(f"Uploaded file to S3: {s3_key}")
            
            # Return CDN URL
            if self.cdn_url:
                return f"{self.cdn_url}/{s3_key}"
            else:
                return f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
            
        except ClientError as e:
            logger.error(f"S3 upload error: {e}")
            raise
    
    async def generate_presigned_url(
        self,
        s3_key: str,
        expiration: int = 3600,
        http_method: str = 'GET'
    ) -> str:
        """
        Generate a presigned URL for temporary access.
        """
        if not self.s3_client:
            raise ValueError("S3 not configured")
            
        try:
            url = self.s3_client.generate_presigned_url(
                ClientMethod='get_object' if http_method == 'GET' else 'put_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': s3_key
                },
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {e}")
            raise
    
    async def delete_file(self, s3_key: str) -> bool:
        """
        Delete file from S3.
        """
        if not self.s3_client:
            return False
            
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            logger.info(f"Deleted file from S3: {s3_key}")
            return True
        except ClientError as e:
            logger.error(f"S3 delete error: {e}")
            return False
    
    async def file_exists(self, s3_key: str) -> bool:
        """
        Check if file exists in S3.
        """
        if not self.s3_client:
            return False
            
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return True
        except ClientError:
            return False


# Singleton instance
_s3_service = None

def get_s3_service() -> S3Service:
    """
    Get S3 service instance (singleton pattern).
    """
    global _s3_service
    if _s3_service is None:
        _s3_service = S3Service()
    return _s3_service
