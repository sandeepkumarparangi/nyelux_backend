#!/usr/bin/env python3
"""
Toggle AI features on/off based on OpenAI availability.
This is NOT a workaround - it's properly disabling features that can't work.
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def toggle_ai_features(enable: bool):
    """Enable or disable AI features in .env file."""
    env_path = ".env"
    
    # Read current .env
    with open(env_path, 'r') as f:
        lines = f.readlines()
    
    # Update or add FEATURE_AI_CHAT
    found = False
    for i, line in enumerate(lines):
        if line.startswith("FEATURE_AI_CHAT="):
            lines[i] = f"FEATURE_AI_CHAT={str(enable).lower()}\n"
            found = True
            break
    
    if not found:
        # Add it after the features section
        for i, line in enumerate(lines):
            if "# Feature Flags" in line:
                lines.insert(i + 1, f"FEATURE_AI_CHAT={str(enable).lower()}\n")
                break
    
    # Write back
    with open(env_path, 'w') as f:
        f.writelines(lines)
    
    print(f"✅ AI features {'enabled' if enable else 'disabled'}")
    print()
    
    if not enable:
        print("AI features are now disabled. The app will start without:")
        print("- Chat endpoints (/api/v1/chat/*)")
        print("- AI-powered device assistance")
        print()
        print("To re-enable when you have OpenAI credits:")
        print("  python3 scripts/toggle_ai.py enable")
    else:
        print("AI features are enabled. Make sure you have OpenAI credits!")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ["enable", "disable"]:
        print("Usage: python3 scripts/toggle_ai.py [enable|disable]")
        sys.exit(1)
    
    enable = sys.argv[1] == "enable"
    toggle_ai_features(enable)
