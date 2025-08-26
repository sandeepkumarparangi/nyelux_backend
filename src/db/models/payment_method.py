"""
Payment Method model for billing functionality.
Stores payment methods for organizations.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.db.base_class import Base


class PaymentMethod(Base):
    """
    Payment method model for storing customer payment information.
    References to actual payment data are stored in Stripe, not here.
    """
    __tablename__ = "payment_methods"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    stripe_payment_method_id = Column(String(255), unique=True, nullable=False)
    type = Column(String(50), nullable=False)  # card, bank_account, etc.
    
    # Card details (last 4 digits only for display)
    card_brand = Column(String(50), nullable=True)  # visa, mastercard, etc.
    card_last4 = Column(String(4), nullable=True)
    card_exp_month = Column(Integer, nullable=True)
    card_exp_year = Column(Integer, nullable=True)
    
    # Bank account details (for ACH)
    bank_name = Column(String(255), nullable=True)
    bank_last4 = Column(String(4), nullable=True)
    
    # Billing details
    billing_name = Column(String(255), nullable=True)
    billing_email = Column(String(255), nullable=True)
    billing_phone = Column(String(50), nullable=True)
    billing_address = Column(JSON, nullable=True)  # JSON with address fields
    
    # Status
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Metadata
    payment_metadata = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    organization = relationship("Organization", back_populates="payment_methods")
