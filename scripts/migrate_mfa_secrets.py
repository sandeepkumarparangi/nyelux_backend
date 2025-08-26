#!/usr/bin/env python
"""
Migrate existing MFA secrets from plain text to encrypted format.
Run this script after deploying the encryption changes.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.db.session import AsyncSessionLocal
from src.db.models.user import User
from src.services.encryption_service import EncryptionService
from src.services.auth_service import AuthService
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_mfa_secrets():
    """Migrate plain text MFA secrets to encrypted format."""
    encryption_service = EncryptionService()
    auth_service = AuthService()
    
    async with AsyncSessionLocal() as db:
        # Find users with plain text MFA secrets
        result = await db.execute(
            select(User).where(
                User.mfa_secret.isnot(None),
                User.mfa_secret_encrypted.is_(None)
            )
        )
        users = result.scalars().all()
        
        if not users:
            logger.info("No users with plain text MFA secrets found.")
            return
        
        logger.info(f"Found {len(users)} users with plain text MFA secrets.")
        
        migrated = 0
        failed = 0
        
        for user in users:
            try:
                # Encrypt MFA secret
                if user.mfa_secret:
                    user.mfa_secret_encrypted = encryption_service.encrypt(user.mfa_secret)
                
                # Hash backup codes if they exist
                if user.mfa_backup_codes:
                    hashed_codes = []
                    for code in user.mfa_backup_codes:
                        hashed = auth_service.get_password_hash(code)
                        hashed_codes.append(hashed)
                    user.mfa_backup_codes_hash = json.dumps(hashed_codes)
                
                # Clear plain text fields
                user.mfa_secret = None
                user.mfa_backup_codes = None
                
                migrated += 1
                logger.info(f"Migrated MFA data for user: {user.email}")
                
            except Exception as e:
                failed += 1
                logger.error(f"Failed to migrate MFA for user {user.email}: {e}")
        
        # Commit all changes
        await db.commit()
        
        logger.info(f"Migration complete. Migrated: {migrated}, Failed: {failed}")


async def verify_migration():
    """Verify that all MFA secrets have been migrated."""
    async with AsyncSessionLocal() as db:
        # Check for any remaining plain text secrets
        result = await db.execute(
            select(User).where(
                User.mfa_secret.isnot(None)
            )
        )
        users_with_plain_text = result.scalars().all()
        
        if users_with_plain_text:
            logger.warning(f"Found {len(users_with_plain_text)} users still with plain text MFA secrets!")
            for user in users_with_plain_text:
                logger.warning(f"  - {user.email}")
        else:
            logger.info("✅ All MFA secrets have been successfully migrated to encrypted format.")
        
        # Check encrypted secrets
        result = await db.execute(
            select(User).where(
                User.mfa_secret_encrypted.isnot(None)
            )
        )
        users_with_encrypted = result.scalars().all()
        logger.info(f"Total users with encrypted MFA: {len(users_with_encrypted)}")


async def main():
    """Run the migration."""
    logger.info("Starting MFA secret migration...")
    await migrate_mfa_secrets()
    
    logger.info("\nVerifying migration...")
    await verify_migration()


if __name__ == "__main__":
    asyncio.run(main())
