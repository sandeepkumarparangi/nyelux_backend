from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, DECIMAL, Enum
from sqlalchemy.orm import relationship
from src.db.base_class import Base
import enum


class SubscriptionStatus(str, enum.Enum):
    """Subscription status enum"""
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"
    TRIALING = "trialing"


class BillingInterval(str, enum.Enum):
    """Billing interval enum"""
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubscriptionTier(Base):
    """
    Subscription tier definitions. REAL implementation.
    Defines available subscription plans and their limits.
    """
    __tablename__ = 'subscription_tiers'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)  # free, basic, professional, enterprise
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    # Pricing
    monthly_price = Column(DECIMAL(10, 2), nullable=False, default=0.00)
    yearly_price = Column(DECIMAL(10, 2), nullable=False, default=0.00)
    
    # Limits
    max_users = Column(Integer, nullable=True)  # NULL = unlimited
    max_devices = Column(Integer, nullable=True)  # NULL = unlimited
    max_storage_gb = Column(Integer, nullable=False, default=10)
    max_api_calls_per_month = Column(Integer, nullable=True)
    
    # Features
    features = Column(Text, nullable=False, default='{}')  # JSON
    
    # Configuration
    is_active = Column(Boolean, default=True, nullable=False)
    is_public = Column(Boolean, default=True, nullable=False)  # Can be selected by new customers
    sort_order = Column(Integer, nullable=False, default=0)
    
    # Relationships
    subscriptions = relationship("Subscription", back_populates="tier")


class Subscription(Base):
    """
    Organization subscription management. REAL implementation.
    Tracks active subscriptions, billing cycles, and usage limits.
    """
    __tablename__ = 'subscriptions'
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, unique=True)
    tier_id = Column(Integer, ForeignKey("subscription_tiers.id"), nullable=False)
    status = Column(Enum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.TRIALING)
    
    # Billing
    billing_interval = Column(Enum(BillingInterval), nullable=False, default=BillingInterval.MONTHLY)
    current_period_start = Column(DateTime(timezone=True), nullable=False)
    current_period_end = Column(DateTime(timezone=True), nullable=False)
    trial_end = Column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Payment
    stripe_customer_id = Column(String(255), nullable=True, unique=True)
    stripe_subscription_id = Column(String(255), nullable=True, unique=True)
    payment_method_last4 = Column(String(4), nullable=True)
    payment_method_brand = Column(String(50), nullable=True)
    next_invoice_date = Column(DateTime(timezone=True), nullable=True)
    
    # Usage limits (override tier defaults)
    custom_max_users = Column(Integer, nullable=True)
    custom_max_devices = Column(Integer, nullable=True)
    custom_max_storage_gb = Column(Integer, nullable=True)
    custom_max_api_calls = Column(Integer, nullable=True)
    
    # Metadata
    notes = Column(Text, nullable=True)
    discount_percentage = Column(DECIMAL(5, 2), nullable=True)
    promo_code = Column(String(50), nullable=True)
    
    # Relationships
    organization = relationship("Organization", back_populates="subscription")
    tier = relationship("SubscriptionTier", back_populates="subscriptions")
    usage_records = relationship("UsageRecord", back_populates="subscription", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="subscription")


class UsageRecord(Base):
    """
    Tracks metered usage for billing purposes. REAL implementation.
    Records all billable events and usage metrics.
    """
    __tablename__ = 'usage_records'
    
    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    
    # Usage tracking
    usage_type = Column(String(50), nullable=False)  # api_calls, storage_gb, ai_tokens, sms_sent
    usage_date = Column(DateTime(timezone=True), nullable=False)
    quantity = Column(DECIMAL(10, 4), nullable=False)
    unit = Column(String(20), nullable=False)  # calls, gb, tokens, messages
    
    # Cost calculation
    unit_price = Column(DECIMAL(10, 6), nullable=True)
    total_cost = Column(DECIMAL(10, 2), nullable=True)
    
    # Metadata
    resource_id = Column(String(255), nullable=True)  # ID of resource that generated usage
    resource_type = Column(String(50), nullable=True)  # chat, api, notification, etc
    usage_metadata = Column(Text, nullable=True)  # JSON with additional details
    
    # Billing
    billed = Column(Boolean, default=False, nullable=False)
    billed_at = Column(DateTime(timezone=True), nullable=True)
    invoice_id = Column(String(255), nullable=True)
    
    # Relationships
    subscription = relationship("Subscription", back_populates="usage_records")
    organization = relationship("Organization")
    
    # Indexes are defined in migration files
