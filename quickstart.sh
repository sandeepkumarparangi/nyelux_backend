#!/bin/bash
# Quick Start Script for Nyelux Backend

echo "🚀 Nyelux Backend - Quick Start Setup"
echo "===================================="

# Check Python version
echo "1. Checking Python version..."
python_version=$(python3 --version 2>&1)
if [[ $? -eq 0 ]]; then
    echo "   ✓ $python_version"
else
    echo "   ✗ Python 3 not found. Please install Python 3.11+"
    exit 1
fi

# Create virtual environment
echo -e "\n2. Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "   ✓ Virtual environment created"
else
    echo "   ✓ Virtual environment already exists"
fi

# Activate virtual environment
echo -e "\n3. Activating virtual environment..."
source venv/bin/activate
echo "   ✓ Virtual environment activated"

# Install dependencies
echo -e "\n4. Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "   ✓ Dependencies installed"

# Create .env file if it doesn't exist
echo -e "\n5. Setting up environment configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "   ✓ Created .env file from template"
    echo "   ⚠️  Please edit .env file with your database credentials"
else
    echo "   ✓ .env file already exists"
fi

# Create logs directory
echo -e "\n6. Creating logs directory..."
mkdir -p logs
echo "   ✓ Logs directory created"

# Check PostgreSQL
echo -e "\n7. Checking PostgreSQL..."
if command -v psql &> /dev/null; then
    echo "   ✓ PostgreSQL is installed"
    
    # Try to create database
    echo "   Attempting to create database..."
    createdb nyelux_development 2>/dev/null
    if [[ $? -eq 0 ]]; then
        echo "   ✓ Database 'nyelux_development' created"
    else
        echo "   ℹ️  Database might already exist or requires different credentials"
    fi
else
    echo "   ⚠️  PostgreSQL not found. Please install PostgreSQL"
fi

# Test database connection
echo -e "\n8. Testing database connection..."
python test_database.py
if [[ $? -eq 0 ]]; then
    echo "   ✓ Database connection successful!"
else
    echo "   ✗ Database connection failed"
    echo "   Please check your .env file and PostgreSQL setup"
fi

echo -e "\n===================================="
echo "✅ Setup Complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your configuration"
echo "2. Run 'python test_database.py' to verify setup"
echo "3. Start the server with: uvicorn src.main:app --reload"
echo "4. Visit http://localhost:8000/docs for API documentation"
echo ""
echo "Happy coding! 🎉"
