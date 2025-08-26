#!/bin/bash
# Make all scripts executable

echo "Setting executable permissions on scripts..."

chmod +x scripts/test_auth_quick.py
chmod +x scripts/test_org_requirements.py
chmod +x scripts/test_auth.py
chmod +x scripts/start_app.sh
chmod +x scripts/check_startup.py

echo "✅ All scripts are now executable"

echo ""
echo "Available test scripts:"
echo "- scripts/test_auth_quick.py        - Quick auth test"
echo "- scripts/test_org_requirements.py  - Test organization logic"
echo "- scripts/test_auth.py             - Comprehensive auth test"
echo ""
echo "Utility scripts:"
echo "- scripts/start_app.sh             - Start application with checks"
echo "- scripts/check_startup.py         - Check external services"
