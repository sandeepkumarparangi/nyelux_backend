"""
Pydantic schemas for request/response validation.
"""

from src.schemas.base import (
    BaseSchema,
    TimestampMixin,
    PaginationParams,
    PaginatedResponse,
    SuccessResponse,
    ErrorResponse
)

from src.schemas.user import (
    UserBase,
    UserCreate,
    UserUpdate,
    UserResponse,
    UserList,
    Token,
    TokenData,
    LoginRequest,
    LoginResponse,
    PasswordChange,
    PasswordReset,
    PasswordResetConfirm,
    MFAEnable,
    MFAEnableResponse,
    MFAVerify,
    EmailVerification,
    RoleUpdate
)

from src.schemas.organization import (
    OrganizationBase,
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
    OrganizationList,
    DepartmentBase,
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentResponse,
    DepartmentList,
    LicenseUpdate,
    OrganizationVerification
)

from src.schemas.device import (
    GUDIDDeviceBase,
    GUDIDDeviceResponse,
    VendorDeviceBase,
    VendorDeviceCreate,
    VendorDeviceUpdate,
    VendorDeviceResponse,
    DeviceList,
    DeviceSearchRequest,
    DeviceSearchResult,
    DeviceSearchResponse,
    DeviceComparisonRequest,
    DeviceComparisonResponse,
    DeviceAnalytics,
    DeviceEngagement
)

from src.schemas.calendar import (
    CalendarEventBase,
    CalendarEventCreate,
    CalendarEventUpdate,
    CalendarEventResponse,
    EventAttendeeBase,
    EventAttendeeResponse,
    EventRSVP,
    AvailabilitySlotBase,
    AvailabilitySlotCreate,
    AvailabilitySlotUpdate,
    AvailabilitySlotResponse,
    AvailabilityRequest,
    AvailabilityResponse,
    GoogleCalendarAuth,
    MicrosoftCalendarAuth,
    CalendarSettings
)

from src.schemas.notification import (
    NotificationBase,
    NotificationCreate,
    NotificationResponse,
    NotificationMarkRead,
    NotificationBulkAction,
    NotificationPreferencesBase,
    NotificationPreferencesUpdate,
    NotificationPreferencesResponse,
    NotificationStats,
    TestNotificationRequest,
    PushSubscription,
    EmailTemplateData
)

from src.schemas.analytics import (
    AnalyticsEventCreate,
    DeviceMetrics,
    DeviceEngagementMetrics,
    DeviceIncidentMetrics,
    DeviceAnalyticsResponse,
    OrganizationMetrics,
    OrganizationDashboardResponse,
    SearchAnalyticsResponse,
    UserActivityResponse,
    IncidentAnalyticsResponse,
    RealtimeMetrics,
    EngagementMetrics,
    TrendAnalysis,
    ExportRequest
)

__all__ = [
    # Base
    "BaseSchema",
    "TimestampMixin",
    "PaginationParams",
    "PaginatedResponse",
    "SuccessResponse",
    "ErrorResponse",
    
    # User
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserList",
    "Token",
    "TokenData",
    "LoginRequest",
    "LoginResponse",
    "PasswordChange",
    "PasswordReset",
    "PasswordResetConfirm",
    "MFAEnable",
    "MFAEnableResponse",
    "MFAVerify",
    "EmailVerification",
    "RoleUpdate",
    
    # Organization
    "OrganizationBase",
    "OrganizationCreate",
    "OrganizationUpdate",
    "OrganizationResponse",
    "OrganizationList",
    "DepartmentBase",
    "DepartmentCreate",
    "DepartmentUpdate",
    "DepartmentResponse",
    "DepartmentList",
    "LicenseUpdate",
    "OrganizationVerification",
    
    # Device
    "GUDIDDeviceBase",
    "GUDIDDeviceResponse",
    "VendorDeviceBase",
    "VendorDeviceCreate",
    "VendorDeviceUpdate",
    "VendorDeviceResponse",
    "DeviceList",
    "DeviceSearchRequest",
    "DeviceSearchResult",
    "DeviceSearchResponse",
    "DeviceComparisonRequest",
    "DeviceComparisonResponse",
    "DeviceAnalytics",
    "DeviceEngagement",
    
    # Calendar
    "CalendarEventBase",
    "CalendarEventCreate",
    "CalendarEventUpdate",
    "CalendarEventResponse",
    "EventAttendeeBase",
    "EventAttendeeResponse",
    "EventRSVP",
    "AvailabilitySlotBase",
    "AvailabilitySlotCreate",
    "AvailabilitySlotUpdate",
    "AvailabilitySlotResponse",
    "AvailabilityRequest",
    "AvailabilityResponse",
    "GoogleCalendarAuth",
    "MicrosoftCalendarAuth",
    "CalendarSettings",
    
    # Notification
    "NotificationBase",
    "NotificationCreate",
    "NotificationResponse",
    "NotificationMarkRead",
    "NotificationBulkAction",
    "NotificationPreferencesBase",
    "NotificationPreferencesUpdate",
    "NotificationPreferencesResponse",
    "NotificationStats",
    "TestNotificationRequest",
    "PushSubscription",
    "EmailTemplateData",
    
    # Analytics
    "AnalyticsEventCreate",
    "DeviceMetrics",
    "DeviceEngagementMetrics",
    "DeviceIncidentMetrics",
    "DeviceAnalyticsResponse",
    "OrganizationMetrics",
    "OrganizationDashboardResponse",
    "SearchAnalyticsResponse",
    "UserActivityResponse",
    "IncidentAnalyticsResponse",
    "RealtimeMetrics",
    "EngagementMetrics",
    "TrendAnalysis",
    "ExportRequest",
]
