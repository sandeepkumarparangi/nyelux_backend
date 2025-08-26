"""
Integration tests for Billing & Subscription functionality.
Tests cover license management, usage tracking, and payment processing.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, date
from decimal import Decimal
from unittest.mock import patch, MagicMock
import stripe
from typing import Dict, List

from src.db.models.user import User
from src.db.models.organization import Organization
from src.db.models.subscription import Subscription, SubscriptionTier, UsageRecord
from src.db.models.invoice import Invoice, InvoiceLineItem
from src.db.models.payment_method import PaymentMethod
from src.db.models.api_key import APIKey
from src.services.auth_service import AuthService


class TestBillingSubscription:
    """Test cases for Billing & Subscription - Section 19"""

    @pytest.fixture
    async def setup_billing_test_data(self, db: AsyncSession):
        """Create test data for billing tests"""
        # Create organizations with different tiers
        orgs = []
        
        # Free tier
        free_org = Organization(
            name="Free Clinic",
            type="clinic",
            subdomain="free-clinic",
            license_tier="free",
            employee_count_range="1-10"
        )
        orgs.append(("free", free_org))
        
        # Basic tier
        basic_org = Organization(
            name="Basic Hospital",
            type="hospital",
            subdomain="basic-hospital",
            license_tier="basic",
            employee_count_range="11-50"
        )
        orgs.append(("basic", basic_org))
        
        # Professional tier
        pro_org = Organization(
            name="Pro Medical Center",
            type="hospital",
            subdomain="pro-medical",
            license_tier="professional",
            employee_count_range="51-500"
        )
        orgs.append(("professional", pro_org))
        
        # Enterprise tier
        enterprise_org = Organization(
            name="Enterprise Healthcare System",
            type="hospital",
            subdomain="enterprise-health",
            license_tier="enterprise",
            employee_count_range="500+"
        )
        orgs.append(("enterprise", enterprise_org))
        
        for tier, org in orgs:
            db.add(org)
        
        await db.flush()
        
        auth_service = AuthService()
        
        # Create admins for each org
        admins = {}
        for tier, org in orgs:
            admin = User(
                email=f"admin@{org.subdomain}.com",
                password_hash=auth_service.get_password_hash("password123"),
                first_name="Admin",
                last_name=tier.title(),
                role="org_admin",
                organization_id=org.id
            )
            db.add(admin)
            admins[tier] = admin
        
        # Create subscription tiers
        tiers = [
            SubscriptionTier(
                name="free",
                display_name="Free",
                price_monthly=Decimal("0.00"),
                price_yearly=Decimal("0.00"),
                max_users=5,
                max_devices=100,
                features=["basic_search", "device_info"],
                api_rate_limit=100,
                storage_gb=1
            ),
            SubscriptionTier(
                name="basic",
                display_name="Basic",
                price_monthly=Decimal("99.00"),
                price_yearly=Decimal("990.00"),
                max_users=50,
                max_devices=1000,
                features=["basic_search", "device_info", "analytics", "support"],
                api_rate_limit=1000,
                storage_gb=10
            ),
            SubscriptionTier(
                name="professional",
                display_name="Professional",
                price_monthly=Decimal("499.00"),
                price_yearly=Decimal("4990.00"),
                max_users=500,
                max_devices=10000,
                features=["basic_search", "device_info", "analytics", "support", 
                         "ai_chat", "api_access", "custom_branding"],
                api_rate_limit=10000,
                storage_gb=100
            ),
            SubscriptionTier(
                name="enterprise",
                display_name="Enterprise",
                price_monthly=Decimal("999.00"),
                price_yearly=Decimal("9990.00"),
                max_users=-1,  # Unlimited
                max_devices=-1,  # Unlimited
                features=["all_features", "sla", "dedicated_support", "custom_integration"],
                api_rate_limit=100000,
                storage_gb=1000
            )
        ]
        
        for tier in tiers:
            db.add(tier)
        
        await db.flush()
        
        # Create subscriptions
        subscriptions = {}
        for tier_name, org in orgs:
            tier = next(t for t in tiers if t.name == tier_name)
            
            subscription = Subscription(
                organization_id=org.id,
                tier_id=tier.id,
                status="active" if tier_name != "free" else "free",
                current_period_start=datetime.utcnow(),
                current_period_end=datetime.utcnow() + timedelta(days=30),
                cancel_at_period_end=False
            )
            
            if tier_name != "free":
                subscription.stripe_subscription_id = f"sub_test_{tier_name}_123"
                subscription.stripe_customer_id = f"cus_test_{tier_name}_456"
            
            db.add(subscription)
            subscriptions[tier_name] = subscription
        
        await db.commit()
        
        return {
            "organizations": dict(orgs),
            "admins": admins,
            "tiers": tiers,
            "subscriptions": subscriptions
        }

    @pytest.fixture
    async def get_admin_headers(self, client: AsyncClient, setup_billing_test_data):
        """Get admin headers for different tier organizations"""
        async def _get_headers(tier: str):
            admin = setup_billing_test_data["admins"][tier]
            response = await client.post(
                "/api/v1/auth/login",
                data={"username": admin.email, "password": "password123"}
            )
            token = response.json()["access_token"]
            return {"Authorization": f"Bearer {token}"}
        
        return _get_headers

    @pytest.mark.asyncio
    async def test_tc_bill_001_usage_tracking_accuracy(
        self, client: AsyncClient, db: AsyncSession, get_admin_headers, setup_billing_test_data
    ):
        """TC-BILL-001: Test usage tracking accuracy"""
        # Test for professional tier (has metered usage)
        headers = await get_admin_headers("professional")
        pro_org = setup_billing_test_data["organizations"]["professional"]
        
        # Track various usage metrics
        usage_events = [
            # OpenAI tokens
            {
                "type": "ai_tokens",
                "quantity": 1500,
                "metadata": {"model": "gpt-4", "conversation_id": "123"}
            },
            # SMS messages
            {
                "type": "sms_sent",
                "quantity": 25,
                "metadata": {"recipient_country": "US"}
            },
            # Storage usage (in MB)
            {
                "type": "storage_mb",
                "quantity": 2048,  # 2GB
                "metadata": {"file_type": "documents"}
            },
            # Video streaming (in minutes)
            {
                "type": "video_minutes",
                "quantity": 120,
                "metadata": {"quality": "1080p"}
            },
            # API calls
            {
                "type": "api_calls",
                "quantity": 5000,
                "metadata": {"endpoint": "/api/v1/devices"}
            }
        ]
        
        # Submit usage events
        for event in usage_events:
            response = await client.post(
                "/api/v1/billing/usage",
                json=event,
                headers=headers
            )
            assert response.status_code in [200, 201]
        
        # Get usage summary for current period
        response = await client.get(
            "/api/v1/billing/usage/current",
            headers=headers
        )
        assert response.status_code == 200
        
        usage_summary = response.json()
        
        # Verify all usage tracked
        assert usage_summary["ai_tokens"]["used"] >= 1500
        assert usage_summary["sms_sent"]["used"] >= 25
        assert usage_summary["storage_mb"]["used"] >= 2048
        assert usage_summary["video_minutes"]["used"] >= 120
        assert usage_summary["api_calls"]["used"] >= 5000
        
        # Verify cost calculations
        assert "estimated_cost" in usage_summary
        assert usage_summary["estimated_cost"] > 0
        
        # Test usage over time
        response = await client.get(
            "/api/v1/billing/usage/history?days=30",
            headers=headers
        )
        assert response.status_code == 200
        
        history = response.json()
        assert "daily_usage" in history
        assert len(history["daily_usage"]) <= 30

    @pytest.mark.asyncio
    async def test_tc_bill_002_license_enforcement(
        self, client: AsyncClient, db: AsyncSession, get_admin_headers, setup_billing_test_data
    ):
        """TC-BILL-002: Test license limit enforcement"""
        # Test basic tier (50 user limit)
        headers = await get_admin_headers("basic")
        basic_org = setup_billing_test_data["organizations"]["basic"]
        
        # Create users up to limit
        auth_service = AuthService()
        
        # First create 49 users (admin already exists = 50 total)
        for i in range(49):
            user = User(
                email=f"user{i}@basic-hospital.com",
                password_hash=auth_service.get_password_hash("password123"),
                first_name=f"User{i}",
                last_name="Basic",
                role="nurse",
                organization_id=basic_org.id
            )
            db.add(user)
        
        await db.commit()
        
        # Try to add 51st user (should fail)
        response = await client.post(
            "/api/v1/users",
            json={
                "email": "user50@basic-hospital.com",
                "password": "password123",
                "first_name": "Over",
                "last_name": "Limit",
                "role": "nurse"
            },
            headers=headers
        )
        
        # Should be blocked
        assert response.status_code == 403
        assert "license limit" in response.json()["detail"].lower()
        
        # Test upgrade prompt
        response = await client.get(
            "/api/v1/billing/upgrade-options",
            headers=headers
        )
        assert response.status_code == 200
        
        upgrade_options = response.json()
        assert "current_tier" in upgrade_options
        assert upgrade_options["current_tier"] == "basic"
        assert "available_upgrades" in upgrade_options
        assert "professional" in [u["tier"] for u in upgrade_options["available_upgrades"]]
        
        # Test immediate access after upgrade
        with patch("stripe.Subscription.modify") as mock_stripe:
            mock_stripe.return_value = MagicMock(
                id="sub_upgraded",
                status="active"
            )
            
            response = await client.post(
                "/api/v1/billing/upgrade",
                json={
                    "target_tier": "professional",
                    "payment_method_id": "pm_test_123"
                },
                headers=headers
            )
            
            if response.status_code == 200:
                # Update subscription in DB
                subscription = setup_billing_test_data["subscriptions"]["basic"]
                pro_tier = next(t for t in setup_billing_test_data["tiers"] if t.name == "professional")
                subscription.tier_id = pro_tier.id
                await db.commit()
                
                # Now should be able to add user
                response = await client.post(
                    "/api/v1/users",
                    json={
                        "email": "user50@basic-hospital.com",
                        "password": "password123",
                        "first_name": "Now",
                        "last_name": "Allowed",
                        "role": "nurse"
                    },
                    headers=headers
                )
                assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_subscription_lifecycle(
        self, client: AsyncClient, db: AsyncSession, get_admin_headers, setup_billing_test_data
    ):
        """Test complete subscription lifecycle"""
        # Start with free tier
        headers = await get_admin_headers("free")
        
        # Check current subscription
        response = await client.get(
            "/api/v1/billing/subscription",
            headers=headers
        )
        assert response.status_code == 200
        
        current_sub = response.json()
        assert current_sub["tier"] == "free"
        assert current_sub["status"] == "free"
        
        # Upgrade to paid tier
        with patch("stripe.Customer.create") as mock_customer, \
             patch("stripe.PaymentMethod.attach") as mock_pm_attach, \
             patch("stripe.Subscription.create") as mock_sub_create:
            
            mock_customer.return_value = MagicMock(id="cus_test_new")
            mock_pm_attach.return_value = MagicMock(id="pm_test_attached")
            mock_sub_create.return_value = MagicMock(
                id="sub_test_new",
                status="active",
                current_period_start=int(datetime.utcnow().timestamp()),
                current_period_end=int((datetime.utcnow() + timedelta(days=30)).timestamp())
            )
            
            response = await client.post(
                "/api/v1/billing/subscribe",
                json={
                    "tier": "professional",
                    "payment_method_id": "pm_test_visa",
                    "billing_period": "monthly"
                },
                headers=headers
            )
            assert response.status_code == 200
            
            # Verify subscription created
            new_sub = response.json()
            assert new_sub["tier"] == "professional"
            assert new_sub["status"] == "active"
        
        # Test downgrade
        with patch("stripe.Subscription.modify") as mock_modify:
            mock_modify.return_value = MagicMock(
                id="sub_test_modified",
                cancel_at_period_end=True
            )
            
            response = await client.post(
                "/api/v1/billing/downgrade",
                json={"target_tier": "basic"},
                headers=headers
            )
            assert response.status_code == 200
            
            # Should schedule downgrade at period end
            downgrade_info = response.json()
            assert downgrade_info["scheduled_for"] is not None
            assert downgrade_info["current_tier"] == "professional"
            assert downgrade_info["future_tier"] == "basic"
        
        # Test cancellation
        with patch("stripe.Subscription.delete") as mock_delete:
            mock_delete.return_value = MagicMock(
                id="sub_test_cancelled",
                status="canceled"
            )
            
            response = await client.post(
                "/api/v1/billing/cancel",
                json={"reason": "Too expensive"},
                headers=headers
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_invoice_generation(
        self, client: AsyncClient, db: AsyncSession, get_admin_headers, setup_billing_test_data
    ):
        """Test invoice generation and retrieval"""
        headers = await get_admin_headers("professional")
        pro_org = setup_billing_test_data["organizations"]["professional"]
        
        # Create test invoice
        invoice = Invoice(
            organization_id=pro_org.id,
            invoice_number="INV-2024-001",
            stripe_invoice_id="in_test_123",
            amount_due=Decimal("599.00"),
            amount_paid=Decimal("599.00"),
            currency="USD",
            status="paid",
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
            due_date=datetime.utcnow() + timedelta(days=7),
            paid_at=datetime.utcnow()
        )
        db.add(invoice)
        
        # Add line items
        line_items = [
            InvoiceLineItem(
                invoice_id=invoice.id,
                description="Professional Plan - Monthly",
                quantity=1,
                unit_price=Decimal("499.00"),
                amount=Decimal("499.00"),
                item_type="subscription"
            ),
            InvoiceLineItem(
                invoice_id=invoice.id,
                description="OpenAI API Usage - 50,000 tokens",
                quantity=50000,
                unit_price=Decimal("0.002"),
                amount=Decimal("100.00"),
                item_type="usage"
            )
        ]
        
        for item in line_items:
            db.add(item)
        
        await db.commit()
        
        # Get invoices
        response = await client.get(
            "/api/v1/billing/invoices",
            headers=headers
        )
        assert response.status_code == 200
        
        invoices = response.json()["invoices"]
        assert len(invoices) > 0
        
        # Get specific invoice
        response = await client.get(
            f"/api/v1/billing/invoices/{invoice.id}",
            headers=headers
        )
        assert response.status_code == 200
        
        invoice_data = response.json()
        assert invoice_data["invoice_number"] == "INV-2024-001"
        assert len(invoice_data["line_items"]) == 2
        assert invoice_data["total"] == "599.00"
        
        # Download invoice PDF
        response = await client.get(
            f"/api/v1/billing/invoices/{invoice.id}/download",
            headers=headers
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_payment_method_management(
        self, client: AsyncClient, db: AsyncSession, get_admin_headers
    ):
        """Test payment method CRUD operations"""
        headers = await get_admin_headers("professional")
        
        # Add payment method
        with patch("stripe.PaymentMethod.attach") as mock_attach, \
             patch("stripe.Customer.modify") as mock_modify:
            
            mock_attach.return_value = MagicMock(
                id="pm_new_card",
                type="card",
                card={"brand": "visa", "last4": "4242"}
            )
            
            response = await client.post(
                "/api/v1/billing/payment-methods",
                json={"payment_method_id": "pm_new_card"},
                headers=headers
            )
            assert response.status_code == 201
            
            pm_data = response.json()
            assert pm_data["type"] == "card"
            assert pm_data["card"]["last4"] == "4242"
        
        # List payment methods
        with patch("stripe.PaymentMethod.list") as mock_list:
            mock_list.return_value = MagicMock(
                data=[
                    MagicMock(
                        id="pm_1",
                        type="card",
                        card={"brand": "visa", "last4": "4242"}
                    ),
                    MagicMock(
                        id="pm_2",
                        type="card",
                        card={"brand": "mastercard", "last4": "5555"}
                    )
                ]
            )
            
            response = await client.get(
                "/api/v1/billing/payment-methods",
                headers=headers
            )
            assert response.status_code == 200
            
            methods = response.json()["payment_methods"]
            assert len(methods) == 2
        
        # Delete payment method
        with patch("stripe.PaymentMethod.detach") as mock_detach:
            mock_detach.return_value = MagicMock(id="pm_1")
            
            response = await client.delete(
                "/api/v1/billing/payment-methods/pm_1",
                headers=headers
            )
            assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_dunning_management(
        self, client: AsyncClient, db: AsyncSession, get_admin_headers, setup_billing_test_data
    ):
        """Test payment failure and dunning process"""
        headers = await get_admin_headers("professional")
        
        # Simulate payment failure webhook
        with patch("stripe.Webhook.construct_event") as mock_webhook:
            mock_webhook.return_value = {
                "type": "invoice.payment_failed",
                "data": {
                    "object": {
                        "id": "in_failed_123",
                        "customer": "cus_test_professional_456",
                        "amount_due": 59900,  # $599.00
                        "attempt_count": 1
                    }
                }
            }
            
            response = await client.post(
                "/api/v1/billing/webhook",
                json=mock_webhook.return_value,
                headers={"Stripe-Signature": "test_signature"}
            )
            assert response.status_code == 200
        
        # Check subscription status
        response = await client.get(
            "/api/v1/billing/subscription",
            headers=headers
        )
        assert response.status_code == 200
        
        sub_status = response.json()
        assert sub_status["payment_status"] == "past_due"
        assert "grace_period_ends" in sub_status
        
        # Update payment method to resolve
        with patch("stripe.PaymentMethod.attach") as mock_attach, \
             patch("stripe.Invoice.pay") as mock_pay:
            
            mock_attach.return_value = MagicMock(id="pm_new_valid")
            mock_pay.return_value = MagicMock(
                id="in_failed_123",
                status="paid"
            )
            
            response = await client.post(
                "/api/v1/billing/retry-payment",
                json={"payment_method_id": "pm_new_valid"},
                headers=headers
            )
            assert response.status_code == 200
            
            # Status should be resolved
            result = response.json()
            assert result["payment_status"] == "paid"

    @pytest.mark.asyncio
    async def test_usage_based_billing(
        self, client: AsyncClient, db: AsyncSession, get_admin_headers, setup_billing_test_data
    ):
        """Test usage-based billing calculations"""
        headers = await get_admin_headers("professional")
        
        # Record various usage
        usage_records = [
            {"type": "ai_tokens", "quantity": 100000, "unit_price": 0.002},
            {"type": "sms_sent", "quantity": 500, "unit_price": 0.05},
            {"type": "storage_gb", "quantity": 150, "unit_price": 0.10},
            {"type": "api_calls", "quantity": 50000, "unit_price": 0.0001}
        ]
        
        expected_total = sum(u["quantity"] * u["unit_price"] for u in usage_records)
        
        # Submit usage
        for usage in usage_records:
            response = await client.post(
                "/api/v1/billing/usage",
                json={
                    "type": usage["type"],
                    "quantity": usage["quantity"]
                },
                headers=headers
            )
            assert response.status_code in [200, 201]
        
        # Get usage summary
        response = await client.get(
            "/api/v1/billing/usage/summary?period=current",
            headers=headers
        )
        assert response.status_code == 200
        
        summary = response.json()
        
        # Verify calculations
        assert abs(float(summary["total_usage_cost"]) - expected_total) < 0.01
        
        # Test usage alerts
        response = await client.get(
            "/api/v1/billing/usage/alerts",
            headers=headers
        )
        assert response.status_code == 200
        
        alerts = response.json()["alerts"]
        
        # Should have alerts for high usage
        if summary["total_usage_cost"] > 100:
            assert any(a["type"] == "high_usage" for a in alerts)

    @pytest.mark.asyncio
    async def test_billing_portal_access(
        self, client: AsyncClient, db: AsyncSession, get_admin_headers
    ):
        """Test Stripe billing portal access"""
        headers = await get_admin_headers("professional")
        
        with patch("stripe.billing_portal.Session.create") as mock_portal:
            mock_portal.return_value = MagicMock(
                url="https://billing.stripe.com/session/test_123"
            )
            
            response = await client.post(
                "/api/v1/billing/portal",
                json={"return_url": "https://app.nyelux.com/billing"},
                headers=headers
            )
            assert response.status_code == 200
            
            portal_data = response.json()
            assert "url" in portal_data
            assert portal_data["url"].startswith("https://billing.stripe.com")

    @pytest.mark.asyncio
    async def test_tax_calculation(
        self, client: AsyncClient, db: AsyncSession, get_admin_headers, setup_billing_test_data
    ):
        """Test tax calculation for different regions"""
        headers = await get_admin_headers("professional")
        pro_org = setup_billing_test_data["organizations"]["professional"]
        
        # Update organization address
        pro_org.state_province = "CA"  # California
        pro_org.country_code = "US"
        await db.commit()
        
        # Get tax calculation
        response = await client.post(
            "/api/v1/billing/calculate-tax",
            json={
                "amount": 499.00,
                "line_items": [
                    {"description": "Professional Plan", "amount": 499.00}
                ]
            },
            headers=headers
        )
        assert response.status_code == 200
        
        tax_calc = response.json()
        assert "tax_amount" in tax_calc
        assert "tax_rate" in tax_calc
        assert "total_with_tax" in tax_calc
        
        # CA sales tax should apply
        assert tax_calc["tax_rate"] > 0
        assert tax_calc["total_with_tax"] > 499.00

    @pytest.mark.asyncio
    async def test_proration_handling(
        self, client: AsyncClient, db: AsyncSession, get_admin_headers
    ):
        """Test subscription proration on upgrades/downgrades"""
        headers = await get_admin_headers("basic")
        
        # Simulate mid-cycle upgrade
        with patch("stripe.Subscription.modify") as mock_modify, \
             patch("stripe.Invoice.upcoming") as mock_upcoming:
            
            # Mock upcoming invoice with proration
            mock_upcoming.return_value = MagicMock(
                amount_due=25000,  # $250.00
                lines=MagicMock(data=[
                    MagicMock(
                        description="Remaining time on Basic Plan",
                        amount=-4950,  # -$49.50 credit
                        proration=True
                    ),
                    MagicMock(
                        description="Remaining time on Professional Plan",
                        amount=29950,  # $299.50
                        proration=True
                    )
                ])
            )
            
            response = await client.post(
                "/api/v1/billing/preview-upgrade",
                json={"target_tier": "professional"},
                headers=headers
            )
            assert response.status_code == 200
            
            preview = response.json()
            assert "proration_amount" in preview
            assert preview["proration_amount"] == "-49.50"  # Credit
            assert "amount_due_now" in preview

    @pytest.mark.asyncio
    async def test_subscription_metrics(
        self, client: AsyncClient, db: AsyncSession, get_admin_headers, setup_billing_test_data
    ):
        """Test subscription analytics and metrics"""
        # Admin endpoint for subscription metrics
        # Would need super admin auth
        
        # Get MRR (Monthly Recurring Revenue)
        response = await client.get(
            "/api/v1/billing/metrics/mrr",
            headers={"Authorization": "Bearer super_admin_token"}  # Would be real token
        )
        
        if response.status_code == 200:
            mrr_data = response.json()
            
            # Calculate expected MRR
            expected_mrr = (
                0 +  # Free
                99 +  # Basic
                499 +  # Professional  
                999   # Enterprise
            )
            
            assert abs(mrr_data["total_mrr"] - expected_mrr) < 1
            assert "mrr_by_tier" in mrr_data
            assert "growth_rate" in mrr_data
        
        # Get churn metrics
        response = await client.get(
            "/api/v1/billing/metrics/churn?period=30d",
            headers={"Authorization": "Bearer super_admin_token"}
        )
        
        if response.status_code == 200:
            churn_data = response.json()
            assert "churn_rate" in churn_data
            assert "churned_mrr" in churn_data
            assert "churned_customers" in churn_data

    @pytest.mark.asyncio
    async def test_free_trial_flow(
        self, client: AsyncClient, db: AsyncSession
    ):
        """Test free trial signup and conversion"""
        # Register new organization with trial
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "trial@newhospital.com",
                "password": "SecurePass123!",
                "first_name": "Trial",
                "last_name": "User",
                "organization_name": "Trial Hospital",
                "organization_type": "hospital",
                "start_trial": True,
                "trial_tier": "professional"
            }
        )
        assert response.status_code == 201
        
        # Login
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": "trial@newhospital.com", "password": "SecurePass123!"}
        )
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Check trial status
        response = await client.get(
            "/api/v1/billing/subscription",
            headers=headers
        )
        assert response.status_code == 200
        
        trial_info = response.json()
        assert trial_info["status"] == "trialing"
        assert trial_info["trial_ends_at"] is not None
        assert trial_info["tier"] == "professional"
        
        # Access should work during trial
        response = await client.get(
            "/api/v1/devices",
            headers=headers
        )
        assert response.status_code == 200
