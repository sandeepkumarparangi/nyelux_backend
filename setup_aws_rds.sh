#!/bin/bash

echo "=== AWS RDS Database Setup for Nyelux ==="
echo "This script configures your AWS RDS database with the required tables"
echo "while keeping GUDID data in Supabase"
echo ""

# Get AWS RDS connection details from user
echo "Enter your AWS RDS details:"
read -p "RDS Host (e.g., nyelux.xxx.rds.amazonaws.com): " RDS_HOST
read -p "Database name (e.g., nyelux_production): " DB_NAME
read -p "Username: " DB_USER
read -sp "Password: " DB_PASS
echo ""

# Connect to AWS RDS and create tables
PGPASSWORD=$DB_PASS psql -h $RDS_HOST -U $DB_USER -d $DB_NAME << 'EOF'

-- =====================================================
-- NYELUX AWS RDS SCHEMA - Private Business Data
-- GUDID data stays in Supabase, linked by primary_di
-- =====================================================

-- Organizations table (vendors, hospitals, clinics)
CREATE TABLE IF NOT EXISTS organizations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL, -- 'vendor', 'hospital', 'clinic'
    subdomain VARCHAR(100) UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Departments within organizations
CREATE TABLE IF NOT EXISTS departments (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Users table with SSO support
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    email_verified BOOLEAN DEFAULT false,
    phone VARCHAR(20),
    phone_verified BOOLEAN DEFAULT false,
    password_hash VARCHAR(255) NOT NULL,
    
    -- Organization relationship
    organization_id INTEGER REFERENCES organizations(id),
    department_id INTEGER REFERENCES departments(id),
    
    -- Role management
    role VARCHAR(50) NOT NULL,
    sub_role VARCHAR(50),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    title VARCHAR(100),
    
    -- Profile
    avatar_url TEXT,
    bio TEXT,
    
    -- MFA
    mfa_enabled BOOLEAN DEFAULT false,
    mfa_secret VARCHAR(255),
    mfa_backup_codes TEXT[],
    mfa_secret_encrypted BYTEA,
    mfa_backup_codes_hash TEXT,
    
    -- Email verification
    email_verification_token_hash VARCHAR(255),
    email_verification_expires TIMESTAMP WITH TIME ZONE,
    
    -- Preferences
    language_preference VARCHAR(10) DEFAULT 'en',
    timezone VARCHAR(50) DEFAULT 'America/New_York',
    notification_preferences JSONB DEFAULT '{}',
    onboarding_completed BOOLEAN DEFAULT false,
    
    -- Activity tracking
    last_login_at TIMESTAMP WITH TIME ZONE,
    last_activity_at TIMESTAMP WITH TIME ZONE,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,
    
    -- Password reset
    password_reset_token VARCHAR(255),
    password_reset_expires TIMESTAMP WITH TIME ZONE,
    
    -- SSO fields
    google_id VARCHAR(255) UNIQUE,
    azure_id VARCHAR(255) UNIQUE,
    saml_id VARCHAR(255) UNIQUE,
    saml_name_id VARCHAR(255),
    created_via VARCHAR(50) DEFAULT 'registration',
    created_by INTEGER REFERENCES users(id),
    require_password_change BOOLEAN DEFAULT false,
    
    -- Vendor access management
    vendor_id INTEGER REFERENCES organizations(id),
    vendor_device_access TEXT[], -- Array of GUDID primary_di values
    vendor_access_level VARCHAR(50),
    access_expires_at TIMESTAMP WITH TIME ZONE,
    access_granted_at TIMESTAMP WITH TIME ZONE,
    access_granted_by INTEGER REFERENCES users(id),
    access_updated_at TIMESTAMP WITH TIME ZONE,
    access_updated_by INTEGER REFERENCES users(id),
    access_revoked_at TIMESTAMP WITH TIME ZONE,
    access_revoked_by INTEGER REFERENCES users(id),
    access_revoked_reason TEXT,
    
    -- Soft delete
    deleted_at TIMESTAMP WITH TIME ZONE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Vendor-specific device information
-- Links to GUDID devices in Supabase via gudid_primary_di
CREATE TABLE IF NOT EXISTS vendor_devices (
    id SERIAL PRIMARY KEY,
    
    -- LINK TO SUPABASE GUDID DATA
    gudid_primary_di VARCHAR(100) NOT NULL, -- This links to Supabase GUDID
    
    organization_id INTEGER REFERENCES organizations(id) NOT NULL,
    
    -- Vendor-specific data
    internal_sku VARCHAR(100),
    custom_name VARCHAR(500),
    list_price DECIMAL(10,2),
    currency_code VARCHAR(3) DEFAULT 'USD',
    warranty_months INTEGER,
    specifications JSONB,
    features JSONB,
    training_required BOOLEAN DEFAULT false,
    certification_required BOOLEAN DEFAULT false,
    access_level VARCHAR(20) DEFAULT 'public',
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    launch_date TIMESTAMP WITH TIME ZONE,
    discontinue_date TIMESTAMP WITH TIME ZONE,
    replacement_device_id INTEGER REFERENCES vendor_devices(id),
    
    -- Audit
    created_by INTEGER REFERENCES users(id),
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Unique constraint: one vendor can only have one entry per GUDID device
    CONSTRAINT uq_vendor_gudid UNIQUE(organization_id, gudid_primary_di)
);

-- Search history for analytics
CREATE TABLE IF NOT EXISTS search_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    organization_id INTEGER REFERENCES organizations(id),
    search_query TEXT NOT NULL,
    search_type VARCHAR(50),
    filters_applied JSONB,
    results_count INTEGER,
    clicked_gudid_di VARCHAR(100), -- Links to Supabase GUDID
    search_duration_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Device incidents/reports
CREATE TABLE IF NOT EXISTS device_incidents (
    id SERIAL PRIMARY KEY,
    gudid_primary_di VARCHAR(100) NOT NULL, -- Links to Supabase GUDID
    vendor_device_id INTEGER REFERENCES vendor_devices(id),
    reported_by INTEGER REFERENCES users(id),
    organization_id INTEGER REFERENCES organizations(id),
    incident_type VARCHAR(50),
    description TEXT,
    status VARCHAR(50) DEFAULT 'open',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Chat conversations about devices
CREATE TABLE IF NOT EXISTS chat_conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    gudid_primary_di VARCHAR(100), -- Links to Supabase GUDID
    vendor_device_id INTEGER REFERENCES vendor_devices(id),
    title VARCHAR(255),
    context_type VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Analytics events
CREATE TABLE IF NOT EXISTS analytics_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    organization_id INTEGER REFERENCES organizations(id),
    event_type VARCHAR(100),
    gudid_primary_di VARCHAR(100), -- Links to Supabase GUDID when relevant
    vendor_device_id INTEGER REFERENCES vendor_devices(id),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_vendor_devices_gudid ON vendor_devices(gudid_primary_di);
CREATE INDEX IF NOT EXISTS idx_vendor_devices_org ON vendor_devices(organization_id);
CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id);
CREATE INDEX IF NOT EXISTS idx_search_history_gudid ON search_history(clicked_gudid_di);
CREATE INDEX IF NOT EXISTS idx_incidents_gudid ON device_incidents(gudid_primary_di);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $DB_USER;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $DB_USER;

-- Show summary
SELECT 'AWS RDS Tables Created:' as status;
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;

EOF

echo ""
echo "=== AWS RDS Configuration Complete! ==="
echo ""
echo "Architecture Summary:"
echo "- Supabase: FDA GUDID data (4.8M+ public devices)"
echo "- AWS RDS: Private business data (users, organizations, vendors)"
echo "- Link Key: gudid_primary_di (FDA Device Identifier)"
echo ""
echo "Next steps:"
echo "1. Update your .env file with AWS RDS connection string"
echo "2. Restart the server"
