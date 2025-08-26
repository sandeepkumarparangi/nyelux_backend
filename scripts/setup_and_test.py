#!/usr/bin/env python3
"""Complete setup and test script"""
import os
import sys
import subprocess

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def run_command(cmd, description):
    """Run a command and report results"""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.stdout:
        print(result.stdout)
    if result.stderr and result.returncode != 0:
        print(f"Error: {result.stderr}")
    
    return result.returncode == 0

def main():
    """Main setup function"""
    print("NYELUX BACKEND SETUP & TEST")
    print("="*60)
    
    # Change to project directory
    os.chdir(project_root)
    print(f"Working directory: {os.getcwd()}")
    
    # 1. Check Python version
    print(f"\nPython version: {sys.version}")
    
    # 2. Install missing dependencies
    print("\nInstalling dependencies...")
    success = run_command(
        "pip install pyotp==2.9.0 cryptography==41.0.7",
        "Installing security dependencies"
    )
    
    if not success:
        print("Failed to install dependencies. Trying with upgrade...")
        run_command(
            "pip install --upgrade pyotp cryptography",
            "Upgrading security dependencies"
        )
    
    # 3. Test imports
    print("\n" + "="*60)
    print("Testing imports...")
    print("="*60)
    
    try:
        import pyotp
        print("✓ pyotp imported successfully")
    except Exception as e:
        print(f"✗ pyotp import failed: {e}")
        return 1
    
    try:
        from cryptography.fernet import Fernet
        print("✓ cryptography imported successfully")
    except Exception as e:
        print(f"✗ cryptography import failed: {e}")
        return 1
    
    # 4. Run security verification
    print("\n" + "="*60)
    print("Running security verification...")
    print("="*60)
    
    result = subprocess.run(
        [sys.executable, "scripts/verify_security_implementation.py"],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print(f"Errors: {result.stderr}")
    
    # 5. Try to start the app
    print("\n" + "="*60)
    print("Testing application startup...")
    print("="*60)
    
    # First, let's just try importing the app
    try:
        # Set environment variable to disable server start
        os.environ['TESTING'] = '1'
        
        from src.main import app
        print("✓ Application imported successfully")
        
        # Test a simple endpoint
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get("/health")
        print(f"✓ Health check response: {response.json()}")
        
    except Exception as e:
        print(f"✗ Application test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n" + "="*60)
    print("✓ Setup and tests completed!")
    print("="*60)
    print("\nTo start the application, run:")
    print("  python run.py")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
