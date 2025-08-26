from fastapi import APIRouter
from src.core.config import settings

from src.api.v1.endpoints import (
    auth, users, organizations, devices, health, search, gudid_sync, public_hybrid,
    device_search, public_search, advanced_search, public_qa, debug, fast_typeahead,
    ultra_scaled_search, extreme_scale, sso
)

# Import all endpoints
from src.api.v1.endpoints import (
    chat, documents, support, calendar, notifications, analytics,
    vendor_public, vendor_management, hcp_vendor, super_admin, vendor_chat,
    vendor_dynamic  # NEW: Dynamic vendor pages from FDA data
)

api_router = APIRouter()

# Public endpoints (no auth required) - Hybrid approach
api_router.include_router(
    public_hybrid.router,
    prefix="/public",
    tags=["public"]
)

# Enhanced public search with typeahead - MAIN PUBLIC SEARCH
api_router.include_router(
    public_search.router,
    prefix="/public",  # Changed from /public/v2 to /public
    tags=["public-search"]
)

# Ultra-fast typeahead for keystroke search
api_router.include_router(
    fast_typeahead.router,
    prefix="/public",
    tags=["fast-typeahead"]
)

# Ultra-scaled search for production
api_router.include_router(
    ultra_scaled_search.router,
    prefix="/public",
    tags=["ultra-scaled"]
)

# Extreme scale search for billions of requests
api_router.include_router(
    extreme_scale.router,
    prefix="/public",
    tags=["extreme-scale"]
)

# Fast device search (alternate)
api_router.include_router(
    device_search.router,
    prefix="/public/alt",
    tags=["device-search-alt"]
)

# Advanced search with filters and analytics
api_router.include_router(
    advanced_search.router,
    prefix="/public/advanced",
    tags=["advanced-search"]
)

# Public Q&A with question limits
api_router.include_router(
    public_qa.router,
    prefix="/public/qa",
    tags=["public-qa"]
)

# Debug endpoints (remove in production)
api_router.include_router(
    debug.router,
    prefix="/debug",
    tags=["debug"]
)

# Health check
api_router.include_router(
    health.router,
    prefix="/health",
    tags=["health"]
)

# Authentication endpoints
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["authentication"]
)

# SSO and OAuth endpoints
api_router.include_router(
    sso.router,
    prefix="/sso",
    tags=["sso"]
)

# Vendor Authentication & User Provisioning
from src.api.v1.endpoints.vendor import vendor_auth
api_router.include_router(
    vendor_auth.router,
    prefix="/vendor",
    tags=["vendor-auth"]
)

# User management
api_router.include_router(
    users.router,
    prefix="/users",
    tags=["users"]
)

# Organization management
api_router.include_router(
    organizations.router,
    prefix="/organizations",
    tags=["organizations"]
)

# Device management
api_router.include_router(
    devices.router,
    prefix="/devices",
    tags=["devices"]
)

# Search functionality
api_router.include_router(
    search.router,
    prefix="/search",
    tags=["search"]
)

# AI Chat
api_router.include_router(
    chat.router,
    prefix="/chat",
    tags=["chat"]
)

# Document management
api_router.include_router(
    documents.router,
    prefix="/documents",
    tags=["documents"]
)

# Support & Incidents
api_router.include_router(
    support.router,
    prefix="/support",
    tags=["support"]
)

# Calendar & Scheduling
api_router.include_router(
    calendar.router,
    prefix="/calendar",
    tags=["calendar"]
)

# Notifications
api_router.include_router(
    notifications.router,
    prefix="/notifications",
    tags=["notifications"]
)

# Analytics
api_router.include_router(
    analytics.router,
    prefix="/analytics",
    tags=["analytics"]
)

# GUDID Sync - Admin only
api_router.include_router(
    gudid_sync.router,
    prefix="/gudid-sync",
    tags=["gudid-sync"]
)

# NEW: Dynamic Vendor Pages from FDA Data - No database needed!
api_router.include_router(
    vendor_dynamic.router,
    tags=["vendor-dynamic"]
)

# Vendor Portal - Public endpoints (keep for backward compatibility)
api_router.include_router(
    vendor_public.router,
    tags=["vendor-public"]
)

# Vendor Management - Vendor admin endpoints
api_router.include_router(
    vendor_management.router,
    tags=["vendor-management"]
)

# HCP Vendor Interaction - Healthcare professional endpoints
api_router.include_router(
    hcp_vendor.router,
    tags=["hcp-vendor"]
)

# Super Admin - Vendor onboarding and management
api_router.include_router(
    super_admin.router,
    tags=["super-admin"]
)

# Vendor Chat - Chat functionality on vendor pages
api_router.include_router(
    vendor_chat.router,
    tags=["vendor-chat"]
)
