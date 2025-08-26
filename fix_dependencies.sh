#!/bin/bash

# Nyelux Backend - Fix Dependencies Script
# This script performs a clean dependency installation

echo "🔧 Fixing Nyelux Backend Dependencies..."

# Step 1: Clean up existing packages
echo "📦 Removing conflicting packages..."
pip uninstall -y supabase postgrest gotrue realtime storage3 websockets realtime-py 2>/dev/null

# Step 2: Clear pip cache
echo "🗑️ Clearing pip cache..."
pip cache purge

# Step 3: Upgrade pip, setuptools, and wheel
echo "⬆️ Upgrading pip and build tools..."
pip install --upgrade pip setuptools wheel

# Step 4: Install websockets first (specific version)
echo "🔌 Installing websockets..."
pip install websockets==12.0

# Step 5: Install all requirements
echo "📥 Installing requirements..."
pip install -r requirements.txt

# Step 6: Verify critical packages
echo "✅ Verifying installations..."
python -c "import fastapi; print(f'✓ FastAPI {fastapi.__version__}')"
python -c "import sqlalchemy; print(f'✓ SQLAlchemy {sqlalchemy.__version__}')"
python -c "import pydantic; print(f'✓ Pydantic {pydantic.__version__}')"
python -c "import openai; print(f'✓ OpenAI {openai.__version__}')"
python -c "import websockets; print(f'✓ WebSockets {websockets.__version__}')"

echo "✨ Dependencies fixed! Try running the server now."
