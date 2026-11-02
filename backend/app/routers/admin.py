import os
import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db, settings
from app.auth import get_admin_user
from app.models import User, AuditLog
from app.schemas import AuditLogResponse, AuditLogListResponse
from app.services.backup_service import (
    create_online_backup, list_backups, get_backup_dir, validate_sqlite_backup
)

router = APIRouter(prefix="/api/admin", tags=["Admin & Backups"])


@router.post("/backups")
async def create_backup_endpoint(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    Trigger a live online SQLite backup using sqlite3.Connection.backup().
    Safe to execute while the application is actively serving requests.
    """
    # Extract source database path from settings
    db_url = settings.DATABASE_URL
    if not db_url.startswith("sqlite"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Online backup utility is configured for SQLite storage.",
        )
    
    # Path relative to backend root
    source_db_path = db_url.replace("sqlite:///", "").replace("sqlite://", "")
    if source_db_path.startswith("./"):
        source_db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), source_db_path[2:])
    elif not os.path.isabs(source_db_path):
        source_db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), source_db_path)
    
    if not os.path.exists(source_db_path):
        # Fallback to default
        source_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "qr_system.db"))

    try:
        backup_info = create_online_backup(source_db_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate online backup: {str(e)}",
        )
    
    # Audit log
    audit = AuditLog(
        user_id=admin.id,
        action="create_backup",
        entity_type="system",
        status="success",
        details=json.dumps({
            "filename": backup_info["filename"],
            "size_bytes": backup_info["size_bytes"],
            "checksum": backup_info["checksum_sha256"],
        }),
    )
    db.add(audit)
    db.commit()

    return {
        "message": "Live online backup generated successfully",
        "backup": backup_info,
    }


@router.get("/backups")
async def get_backups_list(admin: User = Depends(get_admin_user)):
    """List all available validated backups."""
    backups = list_backups()
    return {"backups": backups, "count": len(backups)}


@router.get("/backups/{filename}/download")
async def download_backup_file(filename: str, admin: User = Depends(get_admin_user)):
    """Download a verified database backup file."""
    # Sanitize filename
    safe_name = os.path.basename(filename)
    if not safe_name.endswith(".db"):
        raise HTTPException(status_code=400, detail="Invalid backup filename format")
    
    backup_path = os.path.join(get_backup_dir(), safe_name)
    if not os.path.exists(backup_path):
        raise HTTPException(status_code=404, detail="Backup file not found")
    
    # Validate integrity before sending
    validation = validate_sqlite_backup(backup_path)
    if not validation["valid"]:
        raise HTTPException(status_code=500, detail=f"Corrupt backup file: {validation.get('error')}")
    
    return FileResponse(
        path=backup_path,
        filename=safe_name,
        media_type="application/x-sqlite3",
    )


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def get_audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    action: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Query append-only audit trail with filtering (admin only)."""
    query = db.query(AuditLog)
    
    if action:
        query = query.filter(AuditLog.action == action)
    if status:
        query = query.filter(AuditLog.status == status)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if start_date:
        query = query.filter(AuditLog.created_at >= start_date)
    if end_date:
        query = query.filter(AuditLog.created_at <= end_date)
    
    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    
    logs = query.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    
    items = []
    for log in logs:
        u_name = log.user.username if log.user else None
        items.append(
            AuditLogResponse(
                id=log.id,
                user_id=log.user_id,
                username=u_name,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                details=log.details,
                status=log.status or "success",
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
        )
    
    return AuditLogListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )

