#!/bin/bash

echo "=== COMPLETE DATABASE SETUP ==="
echo "This will create ALL required tables including GUDID"
echo ""

# Run as the postgres superuser to avoid permission issues
psql -d nyelux_development << 'EOF'

-- Create organizations table if it doesn't exist (needed for foreign keys)
CREATE TABLE IF NOT EXISTS organizations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create GUDID devices table for FDA data
CREATE TABLE IF NOT EXISTS gudid_devices (
    primary_di VARCHAR(100) PRIMARY KEY,
    device_name TEXT NOT NULL,
    manufacturer_name VARCHAR(500),
    manufacturer_di VARCHAR(100),
    brand_name VARCHAR(500),
    model_number VARCHAR(500),
    catalog_number VARCHAR(100),
    device_class VARCHAR(3),
    device_class_name VARCHAR(100),
    product_code VARCHAR(10),
    regulation_number VARCHAR(50),
    gmdn_terms TEXT,
    gmdn_codes VARCHAR(500),
    device_description TEXT,
    device_size_text TEXT,
    mri_safety VARCHAR(100),
    sterile BOOLEAN,
    single_use BOOLEAN,
    implantable BOOLEAN,
    life_supporting BOOLEAN,
    rx_required BOOLEAN,
    otc BOOLEAN,
    search_vector TSVECTOR,
    raw_json JSONB,
    sync_timestamp TIMESTAMP WITH TIME ZONE,
    gudid_version INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for GUDID devices
CREATE INDEX IF NOT EXISTS idx_gudid_device_name ON gudid_devices(device_name);
CREATE INDEX IF NOT EXISTS idx_gudid_manufacturer ON gudid_devices(manufacturer_name);
CREATE INDEX IF NOT EXISTS idx_gudid_model ON gudid_devices(model_number);
CREATE INDEX IF NOT EXISTS idx_gudid_device_class ON gudid_devices(device_class);
CREATE INDEX IF NOT EXISTS idx_gudid_mri_safety ON gudid_devices(mri_safety);

-- Create departments table
CREATE TABLE IF NOT EXISTS departments (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create or update users table with ALL columns
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    email_verified BOOLEAN DEFAULT false,
    phone VARCHAR(20),
    phone_verified BOOLEAN DEFAULT false,
    password_hash VARCHAR(255) NOT NULL,
    organization_id INTEGER REFERENCES organizations(id),
    department_id INTEGER REFERENCES departments(id),
    role VARCHAR(50) NOT NULL,
    sub_role VARCHAR(50),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    title VARCHAR(100),
    avatar_url TEXT,
    bio TEXT,
    mfa_enabled BOOLEAN DEFAULT false,
    mfa_secret VARCHAR(255),
    mfa_backup_codes TEXT[],
    mfa_secret_encrypted BYTEA,
    mfa_backup_codes_hash TEXT,
    email_verification_token_hash VARCHAR(255),
    email_verification_expires TIMESTAMP WITH TIME ZONE,
    language_preference VARCHAR(10) DEFAULT 'en',
    timezone VARCHAR(50) DEFAULT 'America/New_York',
    notification_preferences JSONB DEFAULT '{}',
    onboarding_completed BOOLEAN DEFAULT false,
    last_login_at TIMESTAMP WITH TIME ZONE,
    last_activity_at TIMESTAMP WITH TIME ZONE,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,
    password_reset_token VARCHAR(255),
    password_reset_expires TIMESTAMP WITH TIME ZONE,
    google_id VARCHAR(255) UNIQUE,
    azure_id VARCHAR(255) UNIQUE,
    saml_id VARCHAR(255) UNIQUE,
    saml_name_id VARCHAR(255),
    created_via VARCHAR(50) DEFAULT 'registration',
    created_by INTEGER REFERENCES users(id),
    require_password_change BOOLEAN DEFAULT false,
    vendor_id INTEGER REFERENCES organizations(id),
    vendor_device_access TEXT[],
    vendor_access_level VARCHAR(50),
    access_expires_at TIMESTAMP WITH TIME ZONE,
    access_granted_at TIMESTAMP WITH TIME ZONE,
    access_granted_by INTEGER REFERENCES users(id),
    access_updated_at TIMESTAMP WITH TIME ZONE,
    access_updated_by INTEGER REFERENCES users(id),
    access_revoked_at TIMESTAMP WITH TIME ZONE,
    access_revoked_by INTEGER REFERENCES users(id),
    access_revoked_reason TEXT,
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create vendor_devices table
CREATE TABLE IF NOT EXISTS vendor_devices (
    id SERIAL PRIMARY KEY,
    gudid_device_di VARCHAR(100) REFERENCES gudid_devices(primary_di),
    organization_id INTEGER REFERENCES organizations(id) NOT NULL,
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
    is_active BOOLEAN DEFAULT true,
    launch_date TIMESTAMP WITH TIME ZONE,
    discontinue_date TIMESTAMP WITH TIME ZONE,
    replacement_device_id INTEGER REFERENCES vendor_devices(id),
    created_by INTEGER REFERENCES users(id),
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add any missing columns to existing tables
DO $$ 
BEGIN
    -- Add missing columns to users table if it exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='users') THEN
        -- SSO columns
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='google_id') THEN
            ALTER TABLE users ADD COLUMN google_id VARCHAR(255) UNIQUE;
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='azure_id') THEN
            ALTER TABLE users ADD COLUMN azure_id VARCHAR(255) UNIQUE;
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='saml_id') THEN
            ALTER TABLE users ADD COLUMN saml_id VARCHAR(255) UNIQUE;
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='saml_name_id') THEN
            ALTER TABLE users ADD COLUMN saml_name_id VARCHAR(255);
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='created_via') THEN
            ALTER TABLE users ADD COLUMN created_via VARCHAR(50) DEFAULT 'registration';
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='created_by') THEN
            ALTER TABLE users ADD COLUMN created_by INTEGER REFERENCES users(id);
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='require_password_change') THEN
            ALTER TABLE users ADD COLUMN require_password_change BOOLEAN DEFAULT false;
        END IF;
        
        -- Vendor access columns
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='vendor_id') THEN
            ALTER TABLE users ADD COLUMN vendor_id INTEGER REFERENCES organizations(id);
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='vendor_device_access') THEN
            ALTER TABLE users ADD COLUMN vendor_device_access TEXT[];
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='vendor_access_level') THEN
            ALTER TABLE users ADD COLUMN vendor_access_level VARCHAR(50);
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='access_expires_at') THEN
            ALTER TABLE users ADD COLUMN access_expires_at TIMESTAMP WITH TIME ZONE;
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='access_granted_at') THEN
            ALTER TABLE users ADD COLUMN access_granted_at TIMESTAMP WITH TIME ZONE;
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='access_granted_by') THEN
            ALTER TABLE users ADD COLUMN access_granted_by INTEGER REFERENCES users(id);
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='access_updated_at') THEN
            ALTER TABLE users ADD COLUMN access_updated_at TIMESTAMP WITH TIME ZONE;
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='access_updated_by') THEN
            ALTER TABLE users ADD COLUMN access_updated_by INTEGER REFERENCES users(id);
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='access_revoked_at') THEN
            ALTER TABLE users ADD COLUMN access_revoked_at TIMESTAMP WITH TIME ZONE;
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='access_revoked_by') THEN
            ALTER TABLE users ADD COLUMN access_revoked_by INTEGER REFERENCES users(id);
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='access_revoked_reason') THEN
            ALTER TABLE users ADD COLUMN access_revoked_reason TEXT;
        END IF;
    END IF;
END $$;

-- Create alembic_version table and grant permissions
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Grant all permissions to the postgres user (adjust username if different)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON SCHEMA public TO postgres;

-- Show the tables
\dt

-- Show users table structure
\d users

-- Show gudid_devices table structure
\d gudid_devices

EOF

echo ""
echo "=== Database Setup Complete! ==="
echo "All tables created including:"
echo "- gudid_devices (FDA GUDID data)"
echo "- users (with all auth columns)"
echo "- organizations"
echo "- vendor_devices"
echo ""
echo "You can now restart the server and registration should work."
