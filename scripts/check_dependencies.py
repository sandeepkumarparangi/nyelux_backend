#!/usr/bin/env python3
"""Check installed packages"""
import subprocess
import sys

print("Checking installed packages...\n")

# Check if pyotp is installed
result = subprocess.run([sys.executable, "-m", "pip", "show", "pyotp"], capture_output=True, text=True)
if result.returncode == 0:
    print("✓ pyotp is installed:")
    print(result.stdout)
else:
    print("✗ pyotp is NOT installed")
    print("Installing pyotp...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyotp==2.9.0"])

# Check if cryptography is installed
result = subprocess.run([sys.executable, "-m", "pip", "show", "cryptography"], capture_output=True, text=True)
if result.returncode == 0:
    print("\n✓ cryptography is installed:")
    print(result.stdout)
else:
    print("\n✗ cryptography is NOT installed")
    print("Installing cryptography...")
    subprocess.run([sys.executable, "-m", "pip", "install", "cryptography==41.0.7"])

print("\n" + "="*60)
print("Now testing imports...")
print("="*60)

# Now test the import
try:
    import pyotp
    print("✓ pyotp imported successfully")
    secret = pyotp.random_base32()
    print(f"✓ Generated test secret: {secret[:10]}...")
except Exception as e:
    print(f"✗ pyotp import failed: {e}")

try:
    from cryptography.fernet import Fernet
    print("✓ cryptography.fernet imported successfully")
except Exception as e:
    print(f"✗ cryptography import failed: {e}")
