"""
Invoice and billing models for the Nyelux platform.
Handles invoicing, line items, and payment tracking.
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Index, 
    DECIMAL, Enum, Date, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID
from datetime import datetime
import enum
import uuid

from src.db.base_class import Base


class InvoiceStatus(str, enum.Enum):
    """Invoice status enumeration"""
    DRAFT = "draft"
    PENDING = "pending"
    SENT = "sent"
    PAID = "paid"
    PARTIAL = "partial"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentMethod(str, enum.Enum):
    """Payment method enumeration"""
    CREDIT_CARD = "credit_card"
    ACH = "ach"
    WIRE = "wire"
    CHECK = "check"
    OTHER = "other"


class Invoice(Base):
    """
    Invoice for subscription and usage charges.
    """
    __tablename__ = "invoices"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Invoice identifiers
    invoice_number = Column(String(50), unique=True, nullable=False, index=True)
    invoice_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    
    # Organization and subscription
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True)
    
    # Invoice details
    status = Column(Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.DRAFT)
    issue_date = Column(Date, nullable=False, default=datetime.utcnow)
    due_date = Column(Date, nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    
    # Financial amounts (stored as decimal for precision)
    subtotal = Column(DECIMAL(10, 2), nullable=False, default=0)
    tax_rate = Column(DECIMAL(5, 4), nullable=False, default=0)  # e.g., 0.0875 for 8.75%
    tax_amount = Column(DECIMAL(10, 2), nullable=False, default=0)
    discount_amount = Column(DECIMAL(10, 2), nullable=False, default=0)
    total_amount = Column(DECIMAL(10, 2), nullable=False, default=0)
    paid_amount = Column(DECIMAL(10, 2), nullable=False, default=0)
    balance_due = Column(DECIMAL(10, 2), nullable=False, default=0)
    
    # Payment information
    payment_method = Column(Enum(PaymentMethod), nullable=True)
    payment_date = Column(DateTime(timezone=True), nullable=True)
    payment_reference = Column(String(255), nullable=True)
    
    # Billing details
    bill_to_name = Column(String(255), nullable=False)
    bill_to_email = Column(String(255), nullable=False)
    bill_to_address = Column(Text, nullable=True)
    bill_to_phone = Column(String(50), nullable=True)
    
    # Additional information
    notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)
    terms_and_conditions = Column(Text, nullable=True)
    
    # Additional metadata
    invoice_metadata = Column(JSONB, nullable=False, default=lambda: {})
    
    # Tracking
    sent_at = Column(DateTime(timezone=True), nullable=True)
    reminder_sent_at = Column(DateTime(timezone=True), nullable=True)
    last_viewed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    organization = relationship("Organization", back_populates="invoices")
    subscription = relationship("Subscription", back_populates="invoices")
    line_items = relationship("InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_invoice_org_status', 'organization_id', 'status'),
        Index('idx_invoice_due_date', 'due_date'),
        Index('idx_invoice_issue_date', 'issue_date'),
        CheckConstraint('total_amount >= 0', name='check_invoice_total_positive'),
        CheckConstraint('paid_amount >= 0', name='check_invoice_paid_positive'),
        CheckConstraint('due_date >= issue_date', name='check_invoice_due_after_issue'),
    )
    
    def calculate_totals(self):
        """Recalculate invoice totals based on line items"""
        self.subtotal = sum(item.total for item in self.line_items)
        self.tax_amount = self.subtotal * self.tax_rate
        self.total_amount = self.subtotal + self.tax_amount - self.discount_amount
        self.balance_due = self.total_amount - self.paid_amount
        
        # Update status based on payment
        if self.balance_due <= 0 and self.status != InvoiceStatus.CANCELLED:
            self.status = InvoiceStatus.PAID
        elif self.paid_amount > 0 and self.balance_due > 0:
            self.status = InvoiceStatus.PARTIAL
        elif self.due_date < datetime.utcnow().date() and self.balance_due > 0:
            self.status = InvoiceStatus.OVERDUE
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "invoice_number": self.invoice_number,
            "invoice_uuid": str(self.invoice_uuid),
            "organization_id": self.organization_id,
            "subscription_id": self.subscription_id,
            "status": self.status.value,
            "issue_date": self.issue_date.isoformat(),
            "due_date": self.due_date.isoformat(),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "subtotal": float(self.subtotal),
            "tax_rate": float(self.tax_rate),
            "tax_amount": float(self.tax_amount),
            "discount_amount": float(self.discount_amount),
            "total_amount": float(self.total_amount),
            "paid_amount": float(self.paid_amount),
            "balance_due": float(self.balance_due),
            "payment_method": self.payment_method.value if self.payment_method else None,
            "payment_date": self.payment_date.isoformat() if self.payment_date else None,
            "bill_to_name": self.bill_to_name,
            "bill_to_email": self.bill_to_email,
            "line_items": [item.to_dict() for item in self.line_items],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f"<Invoice {self.invoice_number} - {self.organization.name if self.organization else 'N/A'} - {self.status.value}>"


class InvoiceLineItem(Base):
    """
    Individual line items on an invoice.
    """
    __tablename__ = "invoice_line_items"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Invoice association
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    
    # Line item details
    description = Column(Text, nullable=False)
    item_type = Column(String(50), nullable=False)  # subscription, usage, addon, credit, etc.
    quantity = Column(DECIMAL(10, 4), nullable=False, default=1)
    unit_price = Column(DECIMAL(10, 4), nullable=False)
    total = Column(DECIMAL(10, 2), nullable=False)
    
    # Period for recurring items
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    
    # Reference to source
    reference_type = Column(String(50), nullable=True)  # subscription, usage_record, etc.
    reference_id = Column(Integer, nullable=True)
    
    # Additional metadata
    line_item_metadata = Column(JSONB, nullable=False, default=lambda: {})
    
    # Sort order
    sort_order = Column(Integer, nullable=False, default=0)
    
    # Relationships
    invoice = relationship("Invoice", back_populates="line_items")
    
    # Indexes
    __table_args__ = (
        Index('idx_line_item_invoice', 'invoice_id'),
        Index('idx_line_item_reference', 'reference_type', 'reference_id'),
        CheckConstraint('quantity > 0', name='check_line_item_quantity_positive'),
        CheckConstraint('unit_price >= 0', name='check_line_item_price_non_negative'),
    )
    
    def calculate_total(self):
        """Calculate line item total"""
        self.total = self.quantity * self.unit_price
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "description": self.description,
            "item_type": self.item_type,
            "quantity": float(self.quantity),
            "unit_price": float(self.unit_price),
            "total": float(self.total),
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "reference_type": self.reference_type,
            "reference_id": self.reference_id,
            "metadata": self.line_item_metadata or {},
            "sort_order": self.sort_order,
        }
    
    def __repr__(self):
        return f"<InvoiceLineItem {self.description} - ${self.total}>"
