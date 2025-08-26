"""SSO Services Package"""

from .google_oauth_service import GoogleOAuthService

# Optional imports - only if available
try:
    from .saml_service import SAMLService
except ImportError:
    SAMLService = None  # SAML not configured

try:
    from .invitation_service import InvitationService
except ImportError:
    InvitationService = None  # Invitation service not implemented

__all__ = [
    "GoogleOAuthService",
    "SAMLService",
    "InvitationService"
]
