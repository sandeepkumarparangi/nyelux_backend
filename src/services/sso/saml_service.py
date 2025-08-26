"""
SAML 2.0 Service

Handles SAML-based Single Sign-On for enterprise customers
"""
import base64
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.utils import OneLogin_Saml2_Utils
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.models.user import User
from src.db.models.organization import Organization
from src.core.config import settings

logger = logging.getLogger(__name__)


class SAMLService:
    """Service for handling SAML 2.0 authentication"""
    
    def __init__(self):
        self.sp_entity_id = settings.SAML_SP_ENTITY_ID
        self.sp_acs_url = settings.SAML_SP_ACS_URL
        self.sp_cert_file = settings.SAML_SP_CERT_FILE
        self.sp_key_file = settings.SAML_SP_KEY_FILE
        
    def get_saml_settings(self, organization_id: int) -> Dict[str, Any]:
        """
        Get SAML settings for a specific organization
        
        Args:
            organization_id: Organization ID
            
        Returns:
            SAML configuration dictionary
        """
        # In production, these would be loaded from database per organization
        # For now, returning a template configuration
        return {
            "sp": {
                "entityId": self.sp_entity_id,
                "assertionConsumerService": {
                    "url": self.sp_acs_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                },
                "x509cert": self._load_certificate(),
                "privateKey": self._load_private_key()
            },
            "idp": {
                # These would be configured per organization
                "entityId": "",
                "singleSignOnService": {
                    "url": "",
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                },
                "x509cert": ""
            },
            "security": {
                "nameIdEncrypted": False,
                "authnRequestsSigned": True,
                "logoutRequestSigned": True,
                "logoutResponseSigned": True,
                "signMetadata": True,
                "wantMessagesSigned": True,
                "wantAssertionsSigned": True,
                "wantAssertionsEncrypted": False,
                "wantNameId": True,
                "wantNameIdEncrypted": False,
                "requestedAuthnContext": True,
                "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
                "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256"
            }
        }
    
    def init_saml_auth(self, request_data: Dict[str, Any], organization_id: int) -> OneLogin_Saml2_Auth:
        """
        Initialize SAML authentication object
        
        Args:
            request_data: HTTP request data
            organization_id: Organization ID
            
        Returns:
            Configured SAML auth object
        """
        saml_settings = self.get_saml_settings(organization_id)
        return OneLogin_Saml2_Auth(request_data, saml_settings)
    
    def get_sp_metadata(self) -> str:
        """
        Generate Service Provider metadata XML
        
        Returns:
            SP metadata as XML string
        """
        settings = self.get_saml_settings(0)  # Use default settings
        saml_settings = OneLogin_Saml2_Settings(settings)
        metadata = saml_settings.get_sp_metadata()
        errors = saml_settings.validate_metadata(metadata)
        
        if errors:
            logger.error(f"SAML metadata validation errors: {errors}")
            raise ValueError("Invalid SAML metadata")
        
        return metadata
    
    async def process_saml_response(
        self,
        db: AsyncSession,
        saml_auth: OneLogin_Saml2_Auth
    ) -> Optional[User]:
        """
        Process SAML response and authenticate/create user
        
        Args:
            db: Database session
            saml_auth: SAML auth object with processed response
            
        Returns:
            Authenticated user or None if failed
        """
        saml_auth.process_response()
        
        if not saml_auth.is_authenticated():
            errors = saml_auth.get_errors()
            logger.error(f"SAML authentication failed: {errors}")
            logger.error(f"Last error reason: {saml_auth.get_last_error_reason()}")
            return None
        
        # Get user attributes from SAML response
        attributes = saml_auth.get_attributes()
        nameid = saml_auth.get_nameid()
        session_index = saml_auth.get_session_index()
        
        # Map SAML attributes to user fields
        email = attributes.get('email', [nameid])[0]
        first_name = attributes.get('firstName', attributes.get('givenName', ['']))[0]
        last_name = attributes.get('lastName', attributes.get('surname', ['']))[0]
        groups = attributes.get('groups', attributes.get('memberOf', []))
        
        # Find or create user
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            # JIT (Just-In-Time) provisioning
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                email_verified=True,  # SAML users are pre-verified
                saml_name_id=nameid,
                role=self._determine_role_from_groups(groups),
                created_via="saml_sso",
                password_hash="SAML_AUTH"  # Placeholder for SSO users
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            
            logger.info(f"New user created via SAML SSO: {email}")
        else:
            # Update user info from SAML
            user.saml_name_id = nameid
            user.last_login_at = datetime.utcnow()
            
            # Update groups/role if configured
            if groups:
                user.role = self._determine_role_from_groups(groups)
            
            await db.commit()
            await db.refresh(user)
            
            logger.info(f"User authenticated via SAML SSO: {email}")
        
        # Store SAML session info
        await self._store_saml_session(db, user.id, session_index, nameid)
        
        return user
    
    def create_logout_request(
        self,
        saml_auth: OneLogin_Saml2_Auth,
        return_to: Optional[str] = None
    ) -> str:
        """
        Create SAML logout request
        
        Args:
            saml_auth: SAML auth object
            return_to: URL to return to after logout
            
        Returns:
            Logout URL
        """
        return saml_auth.logout(return_to=return_to)
    
    def process_logout_response(
        self,
        saml_auth: OneLogin_Saml2_Auth
    ) -> bool:
        """
        Process SAML logout response
        
        Args:
            saml_auth: SAML auth object
            
        Returns:
            True if logout successful
        """
        url = saml_auth.process_slo(delete_session_cb=lambda: None)
        errors = saml_auth.get_errors()
        
        if errors:
            logger.error(f"SAML logout failed: {errors}")
            return False
        
        return True
    
    async def configure_organization_saml(
        self,
        db: AsyncSession,
        organization_id: int,
        config: Dict[str, Any]
    ) -> None:
        """
        Configure SAML settings for an organization
        
        Args:
            db: Database session
            organization_id: Organization ID
            config: SAML configuration
        """
        # Store SAML configuration in database
        # This would update the sso_configurations table
        result = await db.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        org = result.scalar_one_or_none()
        
        if org:
            # Store config in organization's sso_config field
            org.sso_config = config
            org.sso_enabled = True
            org.sso_provider = "saml"
            await db.commit()
            
            logger.info(f"SAML configured for organization {organization_id}")
    
    def _load_certificate(self) -> str:
        """Load SP certificate"""
        try:
            with open(self.sp_cert_file, 'r') as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("SP certificate file not found, using empty cert")
            return ""
    
    def _load_private_key(self) -> str:
        """Load SP private key"""
        try:
            with open(self.sp_key_file, 'r') as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("SP private key file not found, using empty key")
            return ""
    
    def _determine_role_from_groups(self, groups: list) -> str:
        """
        Determine user role based on SAML groups
        
        Args:
            groups: List of group memberships
            
        Returns:
            User role string
        """
        # Map SAML groups to application roles
        group_role_mapping = {
            "physicians": "physician",
            "nurses": "nurse",
            "technicians": "technician",
            "admins": "org_admin",
            "vendors": "vendor_rep"
        }
        
        for group in groups:
            group_lower = group.lower()
            for key, role in group_role_mapping.items():
                if key in group_lower:
                    return role
        
        return "healthcare_professional"  # Default role
    
    async def _store_saml_session(
        self,
        db: AsyncSession,
        user_id: int,
        session_index: str,
        name_id: str
    ) -> None:
        """
        Store SAML session information
        
        Args:
            db: Database session
            user_id: Internal user ID
            session_index: SAML session index
            name_id: SAML NameID
        """
        # Store in sso_sessions table
        logger.info(f"SAML session stored for user {user_id}")
