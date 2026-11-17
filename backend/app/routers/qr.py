from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, desc
from typing import Optional, List
from datetime import datetime, timedelta
import io
import csv
import json
from app.database import get_db
from app.auth import get_current_user, get_admin_user
from app.models import User, QRCode, QRStatus, AuditLog, QRScanEvent
from app.schemas import (
    BulkGenerateRequest, QRCodeResponse, QRCodeListResponse, QRInventoryStats
)
from app.services.qr_generator import bulk_generate_qr_codes, get_qr_redirect_url
from app.config import get_settings
from app.core.timezone import to_ist_str, ist_now

settings = get_settings()
router = APIRouter(prefix="/api/qr", tags=["QR Codes"])


def qr_to_response(
    qr: QRCode,
    total_scans: int = 0,
    last_scanned_at: Optional[datetime] = None,
) -> QRCodeResponse:
    """Convert a QRCode model to response schema with IST timestamps and scan stats."""
    return QRCodeResponse(
        id=qr.id,
        qr_id=qr.qr_id,
        token=qr.token,
        status=qr.status.value,
        current_destination=qr.current_destination,
        current_business_name=qr.current_business_name,
        created_at=qr.created_at,
        created_at_ist=to_ist_str(qr.created_at),
        updated_at=qr.updated_at,
        updated_at_ist=to_ist_str(qr.updated_at),
        redirect_url=get_qr_redirect_url(qr.token),
        total_scans=total_scans,
        last_scanned_at_ist=to_ist_str(last_scanned_at),
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
    scan_activity: Optional[str] = Query(None, description="all, has_scans, never_scanned, inactive_30d"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List QR codes with pagination, filtering, search, and scan metrics."""
    query = db.query(QRCode)
    
    if status_filter:
        try:
            qr_status = QRStatus(status_filter)
            query = query.filter(QRCode.status == qr_status)
        except ValueError:
            pass
    
    if search:
        s = search.strip()
        query = query.filter(
            or_(
                QRCode.qr_id.ilike(f"%{s}%"),
                QRCode.current_business_name.ilike(f"%{s}%"),
                QRCode.token.ilike(f"%{s}%"),
                QRCode.current_destination.ilike(f"%{s}%"),
            )
        )
    
    if business:
        query = query.filter(QRCode.current_business_name.ilike(f"%{business.strip()}%"))

    # Scan activity filtering
    if scan_activity and scan_activity != "all":
        redirect_subq = (
            db.query(QRScanEvent.qr_code_id)
            .filter(QRScanEvent.result_type == "redirect")
            .distinct()
        )
        if scan_activity == "has_scans":
            query = query.filter(QRCode.id.in_(redirect_subq))
        elif scan_activity == "never_scanned":
            query = query.filter(~QRCode.id.in_(redirect_subq))
        elif scan_activity == "inactive_30d":
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            recent_subq = (
                db.query(QRScanEvent.qr_code_id)
                .filter(QRScanEvent.result_type == "redirect", QRScanEvent.scanned_at >= thirty_days_ago)
                .distinct()
            )
            query = query.filter(
                QRCode.status.in_([QRStatus.ACTIVE, QRStatus.DISABLED]),
                ~QRCode.id.in_(recent_subq),
            )
    
    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    
    items = query.order_by(QRCode.id.desc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()

    # Pre-fetch scan counts and last scan dates for page items
    item_ids = [qr.id for qr in items]
    scan_stats = {}
    if item_ids:
        rows = (
            db.query(
                QRScanEvent.qr_code_id,
                func.count(QRScanEvent.id).label("cnt"),
                func.max(QRScanEvent.scanned_at).label("last_scanned"),
            )
            .filter(QRScanEvent.result_type == "redirect", QRScanEvent.qr_code_id.in_(item_ids))
            .group_by(QRScanEvent.qr_code_id)
            .all()
        )
        for r in rows:
            scan_stats[r[0]] = (r[1], r[2])
    
    return QRCodeListResponse(
        items=[
            qr_to_response(
                qr,
                total_scans=scan_stats.get(qr.id, (0, None))[0],
                last_scanned_at=scan_stats.get(qr.id, (0, None))[1],
            )
            for qr in items
        ],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/export/csv")
async def export_qr_inventory_csv(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    business: Optional[str] = Query(None),
    mask_token: bool = Query(True, description="Mask tokens with asterisks for security"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export filtered QR inventory to CSV with Asia/Kolkata timestamps."""
    query = db.query(QRCode)
    if status_filter:
        try:
            query = query.filter(QRCode.status == QRStatus(status_filter))
        except ValueError:
            pass
    if search:
        s = search.strip()
        query = query.filter(
            or_(
                QRCode.qr_id.ilike(f"%{s}%"),
                QRCode.current_business_name.ilike(f"%{s}%"),
                QRCode.token.ilike(f"%{s}%"),
            )
        )
    if business:
        query = query.filter(QRCode.current_business_name.ilike(f"%{business.strip()}%"))

    qrs = query.order_by(QRCode.id.asc()).all()

    # Pre-fetch scan counts
    qr_ids = [q.id for q in qrs]
    scan_stats = {}
    if qr_ids:
        rows = (
            db.query(
                QRScanEvent.qr_code_id,
                func.count(QRScanEvent.id),
                func.max(QRScanEvent.scanned_at),
            )
            .filter(QRScanEvent.result_type == "redirect", QRScanEvent.qr_code_id.in_(qr_ids))
            .group_by(QRScanEvent.qr_code_id)
            .all()
        )
        for r in rows:
            scan_stats[r[0]] = (r[1], r[2])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "QR ID",
        "Business Name",
        "Token",
        "Destination URL",
        "Status",
        "Total Scans",
        "Last Scanned (IST)",
        "Created At (IST)",
    ])

    for q in qrs:
        cnt, last_scan = scan_stats.get(q.id, (0, None))
        token_str = (q.token[:4] + "••••••••" if mask_token else q.token)
        writer.writerow([
            q.qr_id,
            q.current_business_name or "Unassigned",
            token_str,
            q.current_destination or "",
            q.status.value.upper(),
            cnt,
            to_ist_str(last_scan) if last_scan else "Never",
            to_ist_str(q.created_at),
        ])

    output.seek(0)
    filename = f"qr_inventory_{ist_now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/stats", response_model=QRInventoryStats)
async def get_inventory_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get live inventory counts: total, unassigned, active, disabled, retired."""
    total = db.query(func.count(QRCode.id)).scalar() or 0
    unassigned = db.query(func.count(QRCode.id)).filter(QRCode.status == QRStatus.UNASSIGNED).scalar() or 0
    active = db.query(func.count(QRCode.id)).filter(QRCode.status == QRStatus.ACTIVE).scalar() or 0
    disabled = db.query(func.count(QRCode.id)).filter(QRCode.status == QRStatus.DISABLED).scalar() or 0
    retired = db.query(func.count(QRCode.id)).filter(QRCode.status == QRStatus.RETIRED).scalar() or 0
    
    return QRInventoryStats(
        total=total,
        unassigned=unassigned,
        active=active,
        disabled=disabled,
        retired=retired,
    )


@router.get("/businesses", response_model=List[str])
async def get_distinct_businesses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get list of distinct business names assigned so far."""
    rows = db.query(QRCode.current_business_name).filter(QRCode.current_business_name.isnot(None)).distinct().all()
    return sorted(list(set(r[0] for r in rows if r[0])))


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


@router.get("/{qr_id_or_db_id}/analytics")
async def get_qr_analytics(
    qr_id_or_db_id: str,
    days: int = Query(30, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get scan metrics, trends, and recent events for a single QR code in Asia/Kolkata time."""
    from app.services.analytics import get_single_qr_analytics
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

    return get_single_qr_analytics(db, qr, days=days)
