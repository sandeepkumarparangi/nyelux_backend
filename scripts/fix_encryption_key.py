#!/usr/bin/env python3
"""Generate and update encryption key in .env file"""
import os
import sys
from cryptography.fernet import Fernet

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def main():
    # Generate a new valid key
    key = Fernet.generate_key()
    key_str = key.decode('utf-8')
    
    print("Generated new encryption key:")
    print("="*60)
    print(key_str)
    print("="*60)
    
    # Read the .env file
    env_file = os.path.join(project_root, '.env')
    
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            lines = f.readlines()
        
        # Update the ENCRYPTION_KEY line
        updated = False
        for i, line in enumerate(lines):
            if line.strip().startswith('ENCRYPTION_KEY='):
                lines[i] = f'ENCRYPTION_KEY={key_str}\n'
                updated = True
                break
        
        # If not found, add it after the SECRET_KEY section
        if not updated:
            for i, line in enumerate(lines):
                if line.strip().startswith('ACCESS_TOKEN_EXPIRE_MINUTES='):
                    lines.insert(i + 1, f'\n# Encryption for sensitive data (MFA secrets, etc.)\nENCRYPTION_KEY={key_str}\n')
                    updated = True
                    break
        
        # Write back to file
        if updated:
            with open(env_file, 'w') as f:
                f.writelines(lines)
            print(f"\n✓ Updated ENCRYPTION_KEY in {env_file}")
        else:
            print(f"\n⚠ Could not find location to update ENCRYPTION_KEY in {env_file}")
            print(f"\nPlease add this line manually:")
            print(f"ENCRYPTION_KEY={key_str}")
    else:
        # Create a new .env file with the key
        with open(env_file, 'w') as f:
            f.write(f"# Generated encryption key\nENCRYPTION_KEY={key_str}\n")
        print(f"\n✓ Created {env_file} with new ENCRYPTION_KEY")
    
    print("\n✓ Encryption key setup complete!")
    print("\nYou can now run the application:")
    print("  python run.py")

if __name__ == "__main__":
    main()
