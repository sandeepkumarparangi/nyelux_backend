#!/bin/bash

echo "=== IMMEDIATE DATABASE FIX ==="
echo "Adding missing columns to users table"
echo ""

# Run these SQL commands directly to add the missing columns
psql -d nyelux_development << 'EOF'
-- Add SSO columns if they don't exist
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS azure_id VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS saml_id VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS saml_name_id VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_via VARCHAR(50) DEFAULT 'registration';
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS require_password_change BOOLEAN DEFAULT false;

-- Add vendor access columns
ALTER TABLE users ADD COLUMN IF NOT EXISTS vendor_id INTEGER REFERENCES organizations(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS vendor_device_access TEXT[];
ALTER TABLE users ADD COLUMN IF NOT EXISTS vendor_access_level VARCHAR(50);
ALTER TABLE users ADD COLUMN IF NOT EXISTS access_expires_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS access_granted_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS access_granted_by INTEGER REFERENCES users(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS access_updated_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS access_updated_by INTEGER REFERENCES users(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS access_revoked_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS access_revoked_by INTEGER REFERENCES users(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS access_revoked_reason TEXT;

-- Show the users table structure
\d users
EOF

echo ""
echo "=== Columns added successfully! ==="
echo "The registration endpoint should now work."
echo ""
echo "Restart the server with: ./restart_clean.sh"
