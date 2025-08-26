"""
Application configuration with environment variables.
Uses Pydantic for validation and type safety.
"""

from typing import List, Optional, Union, Dict, Any
from pydantic import AnyHttpUrl, field_validator, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict
import secrets
from functools import lru_cache


class Settings(BaseSettings):
    """
    Application settings with validation.
    All sensitive values must come from environment variables.
    """
    
    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Nyelux Medical Device Intelligence API"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    
    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Encryption for sensitive data (MFA secrets, etc.)
    ENCRYPTION_KEY: Optional[str] = None  # Base64 encoded Fernet key
    
    # Password Policy
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_LOWERCASE: bool = True
    PASSWORD_REQUIRE_NUMBERS: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 100
    RATE_LIMIT_PER_HOUR: int = 1000
    
    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "nyelux_development"
    POSTGRES_PORT: int = 5432
    
    # Database URLs (computed)
    DATABASE_URL: Optional[str] = None
    SYNC_DATABASE_URL: Optional[str] = None
    READ_REPLICA_URL: Optional[str] = None
    
    # Database Pool Configuration
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_TIMEOUT: float = 30.0
    DB_POOL_RECYCLE: int = 3600
    DB_ECHO_SQL: bool = False
    DB_ENABLE_QUERY_LOGGING: bool = False
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_URL: Optional[str] = None
    
    # Elasticsearch
    ELASTICSEARCH_URL: Optional[str] = None
    ELASTICSEARCH_INDEX_PREFIX: str = "nyelux"
    ELASTICSEARCH_TIMEOUT: int = 30
    ELASTICSEARCH_MAX_RETRIES: int = 3
    
    # Cache Configuration
    CACHE_DEFAULT_EXPIRATION: int = 3600  # 1 hour
    CACHE_SEARCH_EXPIRATION: int = 900    # 15 minutes
    CACHE_USER_EXPIRATION: int = 300      # 5 minutes
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    
    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("["):
                # It's a JSON array string
                import json
                try:
                    return json.loads(v)
                except:
                    # If JSON parsing fails, treat as comma-separated
                    return [i.strip() for i in v.split(",")]
            else:
                # Comma-separated string
                return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        return v
    
    # File Upload
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_DOCUMENT_TYPES: List[str] = [
        "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "image/jpeg", "image/png"
    ]
    ALLOWED_VIDEO_TYPES: List[str] = ["video/mp4", "video/quicktime", "video/x-msvideo"]
    UPLOAD_DIR: str = "uploads"
    
    # Document Processing Settings
    MAX_CHUNK_SIZE: int = 1000  # Maximum tokens per chunk
    CHUNK_OVERLAP: int = 200   # Overlap between chunks for context
    MAX_CHUNKS_PER_DOCUMENT: int = 1000  # Limit chunks per document
    
    # External Services
    OPENAI_API_KEY: Optional[str] = None  # Default/Public key
    PUBLIC_OPENAI_API_KEY: Optional[str] = None  # Explicitly for public Q&A
    PRIVATE_OPENAI_API_KEY: Optional[str] = None  # For authenticated/internal features
    OPENAI_MODEL: str = "gpt-3.5-turbo"  # Use gpt-3.5-turbo or gpt-4-turbo if you have access
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-ada-002"
    OPENAI_MAX_TOKENS: int = 500  # Limit for public API
    OPENAI_TEMPERATURE: float = 0.3
    
    # Feature flags for AI
    ENABLE_PUBLIC_AI: bool = True
    ENABLE_PRIVATE_AI: bool = False
    
    # AWS Configuration
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: Optional[str] = None
    S3_BUCKET_REGION: str = "us-east-1"
    S3_USE_SSL: bool = True
    S3_ENDPOINT_URL: Optional[str] = None  # For MinIO/LocalStack
    CLOUDFRONT_URL: Optional[str] = None  # CDN URL for serving files
    
    # Email Configuration
    EMAIL_PROVIDER: str = "sendgrid"  # sendgrid, smtp, or ses
    EMAIL_FROM: str = "noreply@nyelux.com"
    EMAIL_FROM_NAME: str = "Nyelux Medical"
    EMAIL_ENABLED: bool = True
    
    # SendGrid Configuration
    SENDGRID_API_KEY: Optional[str] = None
    SENDGRID_FROM_EMAIL: str = "noreply@nyelux.com"  # Deprecated - use EMAIL_FROM
    SENDGRID_FROM_NAME: str = "Nyelux"  # Deprecated - use EMAIL_FROM_NAME
    
    # SMTP Configuration
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True
    
    # SMS Configuration (Twilio)
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_FROM_NUMBER: Optional[str] = None
    SMS_ENABLED: bool = True
    
    # Google OAuth 2.0 Configuration
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: Optional[str] = None
    
    # Calendar Integration - Google Calendar
    GOOGLE_CALENDAR_CLIENT_ID: Optional[str] = None
    GOOGLE_CALENDAR_CLIENT_SECRET: Optional[str] = None
    GOOGLE_CALENDAR_REDIRECT_URI: Optional[str] = None
    
    # Calendar Integration - Microsoft Graph
    MS_GRAPH_CLIENT_ID: Optional[str] = None
    MS_GRAPH_CLIENT_SECRET: Optional[str] = None
    MS_GRAPH_TENANT_ID: Optional[str] = None
    MS_GRAPH_REDIRECT_URI: Optional[str] = None
    
    # Frontend URL
    FRONTEND_URL: str = "http://localhost:3000"
    
    # FDA GUDID Configuration
    GUDID_DOWNLOAD_URL: str = "https://accessgudid.nlm.nih.gov/download"
    GUDID_SYNC_HOUR: int = 3  # 3 AM EST
    GUDID_SYNC_ENABLED: bool = True
    GUDID_BATCH_SIZE: int = 1000
    
    # Background Jobs
    BACKGROUND_TASK_ENABLED: bool = True
    JOB_QUEUE_NAME: str = "nyelux_jobs"
    MAX_JOB_RETRIES: int = 3
    
    # Monitoring
    SENTRY_DSN: Optional[str] = None
    DATADOG_API_KEY: Optional[str] = None
    DATADOG_APP_KEY: Optional[str] = None
    
    # Supabase
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_SERVICE_KEY: Optional[str] = None  # Service key for backend access (bypasses RLS)
    
    # API Security
    PUBLIC_API_KEY: Optional[str] = None  # API key for public endpoint access
    REQUIRE_API_KEY: bool = True  # Require API key for public endpoints
    
    # Feature Flags
    FEATURE_AI_CHAT: bool = False  # Disabled for now
    FEATURE_VIDEO_STREAMING: bool = True
    FEATURE_DOCUMENT_OCR: bool = True
    FEATURE_CALENDAR_SYNC: bool = True
    FEATURE_REAL_TIME_SUPPORT: bool = True
    ENABLE_EMBEDDINGS: bool = True  # Enable document embeddings if AI is configured
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Build database URLs
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:"
                f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:"
                f"{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        
        if not self.SYNC_DATABASE_URL:
            self.SYNC_DATABASE_URL = (
                f"postgresql://{self.POSTGRES_USER}:"
                f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:"
                f"{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        
        # Build Redis URL
        if not self.REDIS_URL:
            if self.REDIS_PASSWORD:
                self.REDIS_URL = (
                    f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:"
                    f"{self.REDIS_PORT}/{self.REDIS_DB}"
                )
            else:
                self.REDIS_URL = (
                    f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
                )
    
    def get_db_config(self) -> Dict[str, Any]:
        """Get database configuration for session manager."""
        return {
            "database_url": self.DATABASE_URL,
            "read_replica_url": self.READ_REPLICA_URL,
            "pool_size": self.DB_POOL_SIZE,
            "max_overflow": self.DB_MAX_OVERFLOW,
            "pool_timeout": self.DB_POOL_TIMEOUT,
            "pool_recycle": self.DB_POOL_RECYCLE,
            "echo": self.DB_ECHO_SQL,
            "enable_query_logging": self.DB_ENABLE_QUERY_LOGGING,
        }
    
    def validate_external_services(self) -> Dict[str, bool]:
        """Check which external services are configured."""
        return {
            "openai": bool(self.OPENAI_API_KEY),
            "aws_s3": bool(self.AWS_ACCESS_KEY_ID and self.S3_BUCKET_NAME),
            "sendgrid": bool(self.SENDGRID_API_KEY),
            "twilio": bool(self.TWILIO_ACCOUNT_SID and self.TWILIO_AUTH_TOKEN),
            "sentry": bool(self.SENTRY_DSN),
            "datadog": bool(self.DATADOG_API_KEY),
            "elasticsearch": bool(self.ELASTICSEARCH_URL),
        }
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT.lower() == "production"
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT.lower() == "development"
    
    def is_testing(self) -> bool:
        """Check if running in test environment."""
        return self.ENVIRONMENT.lower() in ["test", "testing"]
    
    def has_s3_configured(self) -> bool:
        """Check if S3 is properly configured."""
        return all([
            self.AWS_ACCESS_KEY_ID,
            self.AWS_SECRET_ACCESS_KEY,
            self.S3_BUCKET_NAME
        ])
    
    def has_ai_configured(self) -> bool:
        """Check if AI service is properly configured."""
        return bool(self.OPENAI_API_KEY)
    
    def has_email_configured(self) -> bool:
        """Check if email service is properly configured."""
        return bool(self.SENDGRID_API_KEY and self.EMAIL_ENABLED)
    
    def has_sms_configured(self) -> bool:
        """Check if SMS service is properly configured."""
        return all([
            self.TWILIO_ACCOUNT_SID,
            self.TWILIO_AUTH_TOKEN,
            self.TWILIO_FROM_NUMBER,
            self.SMS_ENABLED
        ])


@lru_cache()
def get_settings() -> Settings:
    """
    Create cached settings instance.
    Use dependency injection in FastAPI:
    
    from src.core.config import get_settings
    
    @router.get("/config")
    def get_config(settings: Settings = Depends(get_settings)):
        return {"environment": settings.ENVIRONMENT}
    """
    return Settings()


# Create a global settings instance for non-DI usage
settings = get_settings()
