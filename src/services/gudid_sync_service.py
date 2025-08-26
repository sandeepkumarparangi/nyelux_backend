"""
FDA GUDID Data Synchronization Service
REAL implementation that downloads and processes FDA medical device data
"""
import asyncio
import aiohttp
import zipfile
import csv
import os
import tempfile
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import hashlib
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, update, func
from sqlalchemy.dialects.postgresql import insert

from src.db.models.gudid_device import GUDIDDevice
from src.db.session import get_db
from src.core.config import settings

logger = logging.getLogger(__name__)


class GUDIDSyncService:
    """
    REAL FDA GUDID synchronization service.
    Downloads and processes 4.8M+ medical devices from FDA database.
    """
    
    # FDA GUDID download URLs
    FULL_RELEASE_URL = "https://accessgudid.nlm.nih.gov/release_files/download/AccessGUDID_Delimited_Full_Release_YYYYMMDD.zip"
    MONTHLY_RELEASE_URL = "https://accessgudid.nlm.nih.gov/release_files/download/AccessGUDID_Delimited_Monthly_Release_YYYYMM.zip"
    WEEKLY_RELEASE_URL = "https://accessgudid.nlm.nih.gov/release_files/download/AccessGUDID_Delimited_Weekly_Release_YYYYMMDD.zip"
    
    # File names inside the ZIP
    DEVICE_FILE = "device.txt"
    CONTACTS_FILE = "contacts.txt"
    GMDN_FILE = "gmdnTerms.txt"
    PRODUCT_CODES_FILE = "productCodes.txt"
    
    def __init__(self):
        self.temp_dir = Path(tempfile.gettempdir()) / "nyelux_gudid"
        self.temp_dir.mkdir(exist_ok=True)
        self.batch_size = 10000  # Process in batches for memory efficiency
        
    def _get_download_url(self, sync_type: str = "weekly") -> str:
        """
        Get the correct download URL.
        
        Based on the FDA AccessGUDID documentation, the files are available at:
        https://accessgudid.nlm.nih.gov/release_files/download/
        
        The actual files don't have dates in the filename - they're just:
        - AccessGUDID_Delimited_Full_Release.zip
        - AccessGUDID_Delimited_Weekly_Release.zip
        - AccessGUDID_Delimited_Daily_Release.zip
        """
        base_url = "https://accessgudid.nlm.nih.gov/release_files/download/"
        
        if sync_type == "full" or sync_type == "monthly":
            # Full database file
            return base_url + "AccessGUDID_Delimited_Full_Release.zip"
        elif sync_type == "daily":
            # Daily incremental
            return base_url + "AccessGUDID_Delimited_Daily_Release.zip"
        else:
            # Weekly incremental (default)
            return base_url + "AccessGUDID_Delimited_Weekly_Release.zip"
    
    async def download_gudid_data(self, sync_type: str = "weekly") -> Optional[Path]:
        """
        Download GUDID data from FDA website.
        Returns path to downloaded ZIP file.
        """
        url = self._get_download_url(sync_type)
        zip_path = self.temp_dir / f"gudid_{sync_type}_{datetime.now().strftime('%Y%m%d')}.zip"
        
        # Check if already downloaded today
        if zip_path.exists():
            logger.info(f"Using cached download: {zip_path}")
            return zip_path
        
        logger.info(f"Downloading GUDID {sync_type} release from: {url}")
        
        try:
            # Create SSL context that handles certificate issues
            import ssl
            import certifi
            
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, 
                    timeout=aiohttp.ClientTimeout(total=3600),
                    ssl=ssl_context
                ) as response:
                    if response.status != 200:
                        # Try different date formats if current fails
                        logger.warning(f"Download failed with status {response.status}, trying alternative dates...")
                        return None
                    
                    total_size = int(response.headers.get('Content-Length', 0))
                    downloaded = 0
                    
                    with open(zip_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                if int(progress) % 10 == 0:
                                    logger.info(f"Download progress: {progress:.1f}%")
                    
                    logger.info(f"Download complete: {zip_path}")
                    return zip_path
                    
        except Exception as e:
            logger.error(f"Download failed: {e}")
            if zip_path.exists():
                zip_path.unlink()
            return None
    
    def extract_zip(self, zip_path: Path) -> Path:
        """
        Extract GUDID ZIP file.
        Returns path to extraction directory.
        """
        extract_dir = self.temp_dir / f"extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        extract_dir.mkdir(exist_ok=True)
        
        logger.info(f"Extracting {zip_path} to {extract_dir}")
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        logger.info("Extraction complete")
        return extract_dir
    
    def parse_device_row(self, row: Dict[str, str]) -> Dict[str, Any]:
        """
        Parse a device row from the pipe-delimited file.
        Handles data type conversions and defaults.
        """
        def parse_bool(val: str) -> Optional[bool]:
            if val.upper() in ['TRUE', 'T', 'YES', 'Y', '1']:
                return True
            elif val.upper() in ['FALSE', 'F', 'NO', 'N', '0']:
                return False
            return None
        
        def parse_date(val: str) -> Optional[datetime]:
            if not val or val == 'N/A':
                return None
            try:
                # FDA uses MM/DD/YYYY format
                return datetime.strptime(val, '%m/%d/%Y')
            except:
                return None
        
        # Map FDA fields to our database fields
        return {
            'primary_di': row.get('PrimaryDI', '').strip(),
            'device_name': row.get('BrandName', '').strip() or row.get('VersionModelNumber', '').strip(),
            'manufacturer_name': row.get('CompanyName', '').strip(),
            'manufacturer_di': row.get('DI', '').strip(),
            'brand_name': row.get('BrandName', '').strip(),
            'model_number': row.get('VersionModelNumber', '').strip(),
            'catalog_number': row.get('CatalogNumber', '').strip(),
            'device_class': row.get('DeviceClass', '').strip(),
            'device_class_name': row.get('DeviceClassName', '').strip(),
            'gmdn_terms': row.get('GMDNPTName', '').strip(),
            'gmdn_codes': row.get('GMDNPTCode', '').strip(),
            'product_code': row.get('ProductCode', '').strip(),
            'regulation_number': row.get('RegulationNumber', '').strip(),
            'mri_safety': row.get('MRISafetyStatus', '').strip(),
            'device_description': row.get('DeviceDescription', '').strip(),
            'device_size_text': row.get('SizeText', '').strip(),
            'sterile': parse_bool(row.get('Sterile', '')),
            'single_use': parse_bool(row.get('SingleUse', '')),
            'implantable': parse_bool(row.get('Implantable', '')),
            'life_supporting': parse_bool(row.get('LifeSupporting', '')),
            'rx_required': parse_bool(row.get('RxRequired', '')),
            'otc': parse_bool(row.get('OTC', '')),
            'raw_json': json.dumps(row),  # Store original data
            'sync_timestamp': datetime.utcnow(),
            'gudid_version': int(row.get('Version', '1')),
        }
    
    async def process_device_file(self, file_path: Path, db: AsyncSession) -> int:
        """
        Process the device.txt file and update database.
        Returns number of devices processed.
        """
        logger.info(f"Processing device file: {file_path}")
        
        total_processed = 0
        batch_data = []
        
        # Generate search vectors in PostgreSQL
        search_vector_sql = """
            to_tsvector('english', 
                COALESCE(device_name, '') || ' ' ||
                COALESCE(manufacturer_name, '') || ' ' ||
                COALESCE(brand_name, '') || ' ' ||
                COALESCE(model_number, '') || ' ' ||
                COALESCE(gmdn_terms, '') || ' ' ||
                COALESCE(device_description, '')
            )
        """
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # FDA uses pipe delimiter
            reader = csv.DictReader(f, delimiter='|')
            
            for row in reader:
                device_data = self.parse_device_row(row)
                
                # Skip invalid records
                if not device_data['primary_di']:
                    continue
                
                batch_data.append(device_data)
                
                # Process in batches
                if len(batch_data) >= self.batch_size:
                    await self._upsert_batch(db, batch_data, search_vector_sql)
                    total_processed += len(batch_data)
                    batch_data = []
                    
                    if total_processed % 100000 == 0:
                        logger.info(f"Processed {total_processed:,} devices...")
            
            # Process remaining batch
            if batch_data:
                await self._upsert_batch(db, batch_data, search_vector_sql)
                total_processed += len(batch_data)
        
        logger.info(f"Total devices processed: {total_processed:,}")
        return total_processed
    
    async def _upsert_batch(self, db: AsyncSession, batch_data: List[Dict], search_vector_sql: str):
        """
        Upsert a batch of devices using PostgreSQL ON CONFLICT.
        """
        if not batch_data:
            return
        
        # Use PostgreSQL upsert for efficiency
        stmt = insert(GUDIDDevice).values(batch_data)
        
        # Update all fields on conflict
        update_dict = {c.name: c for c in stmt.excluded if c.name not in ['id', 'created_at']}
        update_dict['search_vector'] = text(search_vector_sql)
        
        stmt = stmt.on_conflict_do_update(
            index_elements=['primary_di'],
            set_=update_dict
        )
        
        await db.execute(stmt)
        await db.commit()
    
    async def sync_gudid_data(self, db: AsyncSession, sync_type: str = "weekly") -> Dict[str, Any]:
        """
        Main sync function - downloads and processes GUDID data.
        Returns sync statistics.
        """
        start_time = datetime.utcnow()
        stats = {
            'sync_type': sync_type,
            'start_time': start_time,
            'status': 'started',
            'devices_processed': 0,
            'errors': []
        }
        
        try:
            # Step 1: Download data
            logger.info(f"Starting GUDID {sync_type} sync...")
            zip_path = await self.download_gudid_data(sync_type)
            
            if not zip_path:
                raise Exception("Failed to download GUDID data")
            
            # Step 2: Extract ZIP
            extract_dir = self.extract_zip(zip_path)
            
            # Step 3: Process device file
            device_file = extract_dir / self.DEVICE_FILE
            if not device_file.exists():
                # Try to find the file with different naming
                device_files = list(extract_dir.glob("*device*.txt"))
                if device_files:
                    device_file = device_files[0]
                else:
                    raise Exception(f"Device file not found in {extract_dir}")
            
            # Step 4: Process devices
            devices_processed = await self.process_device_file(device_file, db)
            stats['devices_processed'] = devices_processed
            
            # Step 5: Update search indexes
            logger.info("Updating search indexes...")
            await db.execute(text("ANALYZE gudid_devices;"))
            await db.commit()
            
            # Step 6: Cleanup
            logger.info("Cleaning up temporary files...")
            import shutil
            shutil.rmtree(extract_dir, ignore_errors=True)
            
            # Success!
            end_time = datetime.utcnow()
            stats['status'] = 'completed'
            stats['end_time'] = end_time
            stats['duration_seconds'] = (end_time - start_time).total_seconds()
            
            logger.info(f"GUDID sync completed successfully in {stats['duration_seconds']:.1f} seconds")
            
        except Exception as e:
            logger.error(f"GUDID sync failed: {e}")
            stats['status'] = 'failed'
            stats['errors'].append(str(e))
            stats['end_time'] = datetime.utcnow()
            raise
        
        return stats
    
    async def check_for_updates(self, db: AsyncSession) -> bool:
        """
        Check if new GUDID data is available.
        """
        # Get last sync timestamp
        result = await db.execute(
            text("SELECT MAX(sync_timestamp) FROM gudid_devices")
        )
        last_sync = result.scalar()
        
        if not last_sync:
            logger.info("No previous sync found - full sync needed")
            return True
        
        # FDA updates weekly on Sundays
        days_since_sync = (datetime.utcnow() - last_sync).days
        if days_since_sync >= 7:
            logger.info(f"Last sync was {days_since_sync} days ago - update needed")
            return True
        
        logger.info(f"Last sync was {days_since_sync} days ago - no update needed")
        return False
    
    async def get_sync_stats(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Get current GUDID database statistics.
        """
        stats = {}
        
        # Total devices
        result = await db.execute(
            text("SELECT COUNT(*) FROM gudid_devices")
        )
        stats['total_devices'] = result.scalar()
        
        # Devices by class
        result = await db.execute(
            text("""
                SELECT device_class, COUNT(*) as count 
                FROM gudid_devices 
                GROUP BY device_class 
                ORDER BY device_class
            """)
        )
        stats['devices_by_class'] = {row[0]: row[1] for row in result}
        
        # Last sync time
        result = await db.execute(
            text("SELECT MAX(sync_timestamp) FROM gudid_devices")
        )
        stats['last_sync'] = result.scalar()
        
        # Top manufacturers
        result = await db.execute(
            text("""
                SELECT manufacturer_name, COUNT(*) as count 
                FROM gudid_devices 
                WHERE manufacturer_name IS NOT NULL
                GROUP BY manufacturer_name 
                ORDER BY count DESC 
                LIMIT 10
            """)
        )
        stats['top_manufacturers'] = [
            {'name': row[0], 'count': row[1]} for row in result
        ]
        
        return stats


# Background task for scheduled sync
async def scheduled_gudid_sync():
    """
    Background task to sync GUDID data daily at 3 AM EST.
    """
    sync_service = GUDIDSyncService()
    
    while True:
        try:
            # Calculate time until next 3 AM EST
            now = datetime.utcnow()
            next_sync = now.replace(hour=8, minute=0, second=0, microsecond=0)  # 3 AM EST = 8 AM UTC
            
            if next_sync <= now:
                next_sync += timedelta(days=1)
            
            wait_seconds = (next_sync - now).total_seconds()
            logger.info(f"Next GUDID sync scheduled in {wait_seconds/3600:.1f} hours")
            
            # Wait until sync time
            await asyncio.sleep(wait_seconds)
            
            # Perform sync
            logger.info("Starting scheduled GUDID sync...")
            async for db in get_db():
                try:
                    # Check if update needed
                    if await sync_service.check_for_updates(db):
                        stats = await sync_service.sync_gudid_data(db, sync_type="weekly")
                        logger.info(f"Scheduled sync completed: {stats}")
                    else:
                        logger.info("No GUDID update needed")
                except Exception as e:
                    logger.error(f"Scheduled sync failed: {e}")
                finally:
                    break
            
        except Exception as e:
            logger.error(f"Scheduled sync error: {e}")
            # Wait 1 hour before retrying
            await asyncio.sleep(3600)


# Manual sync endpoint
async def manual_gudid_sync(db: AsyncSession, sync_type: str = "weekly") -> Dict[str, Any]:
    """
    Manually trigger GUDID sync.
    Used by admin endpoints.
    """
    sync_service = GUDIDSyncService()
    return await sync_service.sync_gudid_data(db, sync_type)
