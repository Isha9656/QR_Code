from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from app.database import get_db
from app.auth import get_current_user, get_admin_user
from app.models import User, QRCode, QRStatus, AuditLog
from app.schemas import (
    BulkGenerateRequest, QRCodeResponse, QRCodeListResponse
)
from app.services.qr_generator import bulk_generate_qr_codes, get_qr_redirect_url
from app.config import get_settings
import json

settings = get_settings()
router = APIRouter(prefix="/api/qr", tags=["QR Codes"])


def qr_to_response(qr: QRCode) -> QRCodeResponse:
    """Convert a QRCode model to response schema."""
    return QRCodeResponse(
        id=qr.id,
        qr_id=qr.qr_id,
        token=qr.token,
        status=qr.status.value,
        current_destination=qr.current_destination,
        current_business_name=qr.current_business_name,
        created_at=qr.created_at,
        updated_at=qr.updated_at,
        redirect_url=get_qr_redirect_url(qr.token),
    )


@router.post("/bulk-generate", response_model=list[QRCodeResponse])
async def bulk_generate(
    request: BulkGenerateRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Generate QR codes in bulk (admin only)."""
    qr_codes = bulk_generate_qr_codes(db, request.quantity)
    
    # Audit log
    audit = AuditLog(
        user_id=admin.id,
        action="bulk_generate",
        entity_type="qr_code",
        details=json.dumps({
            "quantity": request.quantity,
            "first_id": qr_codes[0].qr_id if qr_codes else None,
            "last_id": qr_codes[-1].qr_id if qr_codes else None,
        }),
    )
    db.add(audit)
    db.commit()
    
    return [qr_to_response(qr) for qr in qr_codes]


@router.get("", response_model=QRCodeListResponse)
async def list_qr_codes(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    business: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List QR codes with pagination, filtering and search."""
    query = db.query(QRCode)
    
    if status_filter:
        try:
            qr_status = QRStatus(status_filter)
            query = query.filter(QRCode.status == qr_status)
        except ValueError:
            pass
    
    if search:
        query = query.filter(
            or_(
                QRCode.qr_id.ilike(f"%{search}%"),
                QRCode.current_business_name.ilike(f"%{search}%"),
                QRCode.token.ilike(f"%{search}%"),
            )
        )
    
    if business:
        query = query.filter(QRCode.current_business_name.ilike(f"%{business}%"))
    
    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    
    items = query.order_by(QRCode.id.desc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()
    
    return QRCodeListResponse(
        items=[qr_to_response(qr) for qr in items],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/{qr_id_or_db_id}", response_model=QRCodeResponse)
async def get_qr_code(
    qr_id_or_db_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single QR code by ID or database ID."""
    qr = None
    if qr_id_or_db_id.startswith("QR-"):
        qr = db.query(QRCode).filter(QRCode.qr_id == qr_id_or_db_id).first()
    else:
        try:
            db_id = int(qr_id_or_db_id)
            qr = db.query(QRCode).filter(QRCode.id == db_id).first()
        except ValueError:
            pass
    
    if not qr:
        raise HTTPException(status_code=404, detail="QR code not found")
    
    return qr_to_response(qr)
