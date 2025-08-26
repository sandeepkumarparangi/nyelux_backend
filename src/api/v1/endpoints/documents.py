"""
Document management API endpoints.
Handles document upload, processing, and retrieval.
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
import logging

from src.api.deps import get_db, get_current_user
from src.db.models.user import User
from src.db.models.device_document import DeviceDocument
from src.db.models.vendor_device import VendorDevice
from src.schemas.document import (
    DocumentResponse,
    DocumentList,
    DocumentCreate,
    DocumentSearchRequest,
    DocumentSearchResult,
    DocumentStats
)
from src.services.document_service import DocumentService
from src.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)
router = APIRouter()

# Create service instances for this router
document_service = DocumentService()
analytics_service = AnalyticsService()


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(...),
    device_id: int = Form(...),
    document_type: str = Form(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    language_code: str = Form("en"),
    access_level: str = Form("public")
) -> DeviceDocument:
    """
    Upload a document for a device.
    
    - **file**: Document file (PDF, Word, Excel, Image)
    - **device_id**: Device this document relates to
    - **document_type**: Type of document (manual, quickstart, datasheet, etc.)
    - **title**: Document title (optional, defaults to filename)
    - **description**: Document description
    - **language_code**: Language code (default: en)
    - **access_level**: Access level (public, restricted, private)
    """
    # Validate document type
    valid_types = ["manual", "quickstart", "datasheet", "certificate", "clinical_study", "safety_notice"]
    if document_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document type. Must be one of: {', '.join(valid_types)}"
        )
    
    # Validate access level
    valid_access_levels = ["public", "restricted", "private"]
    if access_level not in valid_access_levels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid access level. Must be one of: {', '.join(valid_access_levels)}"
        )
    
    # Check user's organization
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User must belong to an organization to upload documents"
        )
    
    try:
        # Upload document
        document = await document_service.upload_document(
            db=db,
            file=file.file,
            filename=file.filename,
            device_id=device_id,
            organization_id=current_user.organization_id,
            document_type=document_type,
            user_id=current_user.id,
            title=title or file.filename,
            description=description,
            language_code=language_code,
            access_level=access_level
        )
        
        # Track analytics
        await analytics_service.track_event(
            db=db,
            user_id=current_user.id,
            organization_id=current_user.organization_id,
            event_type="document_upload",
            event_category="engagement",
            resource_type="document",
            resource_id=str(document.id),
            metadata={
                "device_id": device_id,
                "document_type": document_type,
                "file_size": document.file_size_bytes,
                "mime_type": document.mime_type
            }
        )
        
        return document
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Document upload error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload document"
        )


@router.get("/device/{device_id}", response_model=DocumentList)
async def get_device_documents(
    device_id: int,
    document_type: Optional[str] = None,
    language_code: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get documents for a specific device.
    
    - **document_type**: Filter by document type
    - **language_code**: Filter by language
    - **skip**: Number of documents to skip
    - **limit**: Maximum number of documents to return
    """
    # Build query
    stmt = select(DeviceDocument).where(
        and_(
            DeviceDocument.device_id == device_id,
            DeviceDocument.deleted_at.is_(None),
            DeviceDocument.is_current_version == True
        )
    )
    
    # Apply filters
    if document_type:
        stmt = stmt.where(DeviceDocument.document_type == document_type)
    
    if language_code:
        stmt = stmt.where(DeviceDocument.language_code == language_code)
    
    # Filter by access level
    if current_user.organization_id:
        stmt = stmt.where(
            or_(
                DeviceDocument.access_level == "public",
                DeviceDocument.organization_id == current_user.organization_id
            )
        )
    else:
        stmt = stmt.where(DeviceDocument.access_level == "public")
    
    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt)
    
    # Get documents
    stmt = stmt.order_by(DeviceDocument.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    documents = result.scalars().all()
    
    return {
        "documents": documents,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> DeviceDocument:
    """Get document details by ID."""
    document = await db.get(DeviceDocument, document_id)
    
    if not document or document.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check access
    if document.access_level != "public":
        if not current_user.organization_id or document.organization_id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    
    return document


@router.get("/{document_id}/download")
async def download_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Get presigned URL for document download.
    Tracks download analytics.
    """
    try:
        download_url = await document_service.get_document_url(
            db=db,
            document_id=document_id,
            user_id=current_user.id,
            organization_id=current_user.organization_id,
            action="download"
        )
        
        return {
            "download_url": download_url,
            "expires_in": 3600  # 1 hour
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/search", response_model=List[DocumentResponse])
async def search_documents(
    request: DocumentSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[DeviceDocument]:
    """
    Search documents across devices.
    
    - **query**: Search query
    - **device_id**: Filter by device (optional)
    - **document_types**: Filter by document types
    - **language_codes**: Filter by languages
    """
    results = await document_service.search_documents(
        db=db,
        query=request.query,
        device_id=request.device_id,
        organization_id=current_user.organization_id,
        document_types=[request.document_type] if request.document_type else None,
        limit=20  # DocumentSearchRequest doesn't have a limit field
    )
    
    # Convert to response models
    documents = []
    for result in results:
        doc = await db.get(DeviceDocument, result["id"])
        if doc:
            documents.append(doc)
    
    return documents


@router.put("/{document_id}")
async def update_document(
    document_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    access_level: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> DocumentResponse:
    """
    Update document metadata.
    Only organization admins can update documents.
    """
    document = await db.get(DeviceDocument, document_id)
    
    if not document or document.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check permissions
    if document.organization_id != current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this document"
        )
    
    if current_user.role not in ["org_admin", "vendor_admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can update documents"
        )
    
    # Update fields
    if title is not None:
        document.title = title
    
    if description is not None:
        document.description = description
    
    if access_level is not None:
        if access_level not in ["public", "restricted", "private"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid access level"
            )
        document.access_level = access_level
    
    document.updated_at = func.now()
    await db.commit()
    await db.refresh(document)
    
    return document


@router.delete("/{document_id}")
async def delete_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Soft delete a document.
    Only organization admins can delete documents.
    """
    document = await db.get(DeviceDocument, document_id)
    
    if not document or document.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check permissions
    if document.organization_id != current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this document"
        )
    
    if current_user.role not in ["org_admin", "vendor_admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete documents"
        )
    
    # Soft delete
    document.deleted_at = func.now()
    await db.commit()
    
    return {"message": "Document deleted successfully"}


@router.post("/{document_id}/new-version", response_model=DocumentResponse)
async def upload_new_version(
    document_id: int,
    file: UploadFile = File(...),
    version: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> DeviceDocument:
    """
    Upload a new version of an existing document.
    Previous version is kept but marked as non-current.
    """
    # Get original document
    original = await db.get(DeviceDocument, document_id)
    
    if not original or original.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check permissions
    if original.organization_id != current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this document"
        )
    
    if current_user.role not in ["org_admin", "vendor_admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can upload new versions"
        )
    
    try:
        # Mark current version as non-current
        original.is_current_version = False
        
        # Upload new version
        new_document = await document_service.upload_document(
            db=db,
            file=file.file,
            filename=file.filename,
            device_id=original.device_id,
            organization_id=original.organization_id,
            document_type=original.document_type,
            user_id=current_user.id,
            title=original.title,
            description=original.description,
            language_code=original.language_code,
            access_level=original.access_level
        )
        
        # Set version info
        new_document.version = version
        new_document.previous_version_id = original.id
        
        await db.commit()
        await db.refresh(new_document)
        
        return new_document
        
    except Exception as e:
        logger.error(f"Version upload error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload new version"
        )


@router.get("/stats/summary")
async def get_document_stats(
    device_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get document statistics for organization or device.
    """
    # Base query
    stmt = select(DeviceDocument).where(
        and_(
            DeviceDocument.deleted_at.is_(None),
            DeviceDocument.is_current_version == True
        )
    )
    
    # Filter by organization
    if current_user.organization_id:
        stmt = stmt.where(
            or_(
                DeviceDocument.access_level == "public",
                DeviceDocument.organization_id == current_user.organization_id
            )
        )
    
    # Filter by device if specified
    if device_id:
        stmt = stmt.where(DeviceDocument.device_id == device_id)
    
    result = await db.execute(stmt)
    documents = result.scalars().all()
    
    # Calculate statistics
    stats = {
        "total_documents": len(documents),
        "by_type": {},
        "by_language": {},
        "total_size_mb": sum(doc.file_size_bytes for doc in documents) / (1024 * 1024),
        "total_downloads": sum(doc.download_count for doc in documents),
        "average_page_count": sum(doc.page_count or 0 for doc in documents) / len(documents) if documents else 0
    }
    
    # Group by type
    for doc in documents:
        if doc.document_type not in stats["by_type"]:
            stats["by_type"][doc.document_type] = 0
        stats["by_type"][doc.document_type] += 1
    
    # Group by language
    for doc in documents:
        if doc.language_code not in stats["by_language"]:
            stats["by_language"][doc.language_code] = 0
        stats["by_language"][doc.language_code] += 1
    
    return stats
