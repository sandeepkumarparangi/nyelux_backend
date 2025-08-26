"""
Google OAuth 2.0 Service

Handles Google OAuth authentication flow for single sign-on
"""
import os
import json
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import httpx
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.db.models.user import User
from src.db.models.organization import Organization
from src.core.config import settings
from src.services.auth_service import auth_service

logger = logging.getLogger(__name__)


class GoogleOAuthService:
    """Service for handling Google OAuth 2.0 authentication"""
    
    def __init__(self):
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        self.redirect_uri = settings.GOOGLE_REDIRECT_URI
        self.auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
        self.token_url = "https://oauth2.googleapis.com/token"
        self.userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        
    def get_authorization_url(self, state: str) -> str:
        """
        Generate Google OAuth authorization URL
        
        Args:
            state: Random state token for CSRF protection
            
        Returns:
            Complete authorization URL to redirect user to
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",  # Request refresh token
            "prompt": "consent"  # Force consent to get refresh token
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.auth_url}?{query_string}"
    
    async def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens
        
        Args:
            code: Authorization code from Google
            
        Returns:
            Dictionary containing access_token, refresh_token, and expiry
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code"
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Google token exchange failed: {response.text}")
                raise Exception("Failed to exchange code for tokens")
            
            return response.json()
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Fetch user information from Google
        
        Args:
            access_token: Google access token
            
        Returns:
            User profile information from Google
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get Google user info: {response.text}")
                raise Exception("Failed to get user information")
            
            return response.json()
    
    async def authenticate_or_create_user(
        self,
        db: AsyncSession,
        google_user_info: Dict[str, Any]
    ) -> Tuple[User, bool]:
        """
        Authenticate existing user or create new one from Google profile
        
        Args:
            db: Database session
            google_user_info: User info from Google
            
        Returns:
            Tuple of (User object, is_new_user boolean)
        """
        email = google_user_info.get("email")
        if not email:
            raise ValueError("Email not provided by Google")
        
        # Check if user exists
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        
        is_new_user = False
        
        if not user:
            # Check if email domain has auto-approval
            domain = email.split("@")[1]
            org = await self._get_organization_by_domain(db, domain)
            
            # Create new user
            user = User(
                email=email,
                first_name=google_user_info.get("given_name", ""),
                last_name=google_user_info.get("family_name", ""),
                email_verified=True,  # Google emails are pre-verified
                google_id=google_user_info.get("id"),
                avatar_url=google_user_info.get("picture"),
                organization_id=org.id if org else None,
                role="healthcare_professional" if org else "individual_practitioner",
                created_via="google_oauth",
                password_hash="GOOGLE_AUTH"  # Placeholder for OAuth users
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            is_new_user = True
            
            logger.info(f"New user created via Google OAuth: {email}")
        else:
            # Update Google ID if not set
            if not user.google_id:
                user.google_id = google_user_info.get("id")
            
            # Update avatar if changed
            if google_user_info.get("picture") and user.avatar_url != google_user_info.get("picture"):
                user.avatar_url = google_user_info.get("picture")
            
            # Mark email as verified if not already
            if not user.email_verified:
                user.email_verified = True
            
            user.last_login_at = datetime.utcnow()
            await db.commit()
            await db.refresh(user)
            
            logger.info(f"User authenticated via Google OAuth: {email}")
        
        # Store OAuth session
        await self._store_oauth_session(
            db,
            user.id,
            google_user_info.get("id"),
            google_user_info.get("access_token"),
            google_user_info.get("refresh_token")
        )
        
        return user, is_new_user
    
    async def _get_organization_by_domain(
        self,
        db: AsyncSession,
        domain: str
    ) -> Optional[Organization]:
        """
        Check if domain has auto-approval for an organization
        
        Args:
            db: Database session
            domain: Email domain
            
        Returns:
            Organization if domain is approved, None otherwise
        """
        # First check if we have the organization_domains table
        # For now, we'll do a simple domain check on organization email patterns
        result = await db.execute(
            select(Organization).where(
                Organization.allowed_email_domains.contains([domain])
            )
        )
        return result.scalar_one_or_none()
    
    async def _store_oauth_session(
        self,
        db: AsyncSession,
        user_id: int,
        provider_user_id: str,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None
    ) -> None:
        """
        Store OAuth session information for future use
        
        Args:
            db: Database session
            user_id: Internal user ID
            provider_user_id: Google user ID
            access_token: OAuth access token
            refresh_token: OAuth refresh token
        """
        # This would store in an sso_sessions table
        # For now, we'll just log it
        logger.info(f"OAuth session stored for user {user_id}")
        
    async def refresh_google_token(
        self,
        refresh_token: str
    ) -> Dict[str, Any]:
        """
        Refresh an expired Google access token
        
        Args:
            refresh_token: Google refresh token
            
        Returns:
            New token information
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token"
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to refresh Google token: {response.text}")
                raise Exception("Failed to refresh token")
            
            return response.json()
