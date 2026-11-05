from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import QRCode, QRScanEvent, QRStatus, QRAssignment


def get_overview(db: Session) -> dict:
    """Get analytics overview statistics."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    total = db.query(func.count(QRCode.id)).scalar() or 0
    unassigned = db.query(func.count(QRCode.id)).filter(QRCode.status == QRStatus.UNASSIGNED).scalar() or 0
    active = db.query(func.count(QRCode.id)).filter(QRCode.status == QRStatus.ACTIVE).scalar() or 0
    disabled = db.query(func.count(QRCode.id)).filter(QRCode.status == QRStatus.DISABLED).scalar() or 0
    retired = db.query(func.count(QRCode.id)).filter(QRCode.status == QRStatus.RETIRED).scalar() or 0
    
    # Genuine public redirects (excluding unassigned/invalid/disabled attempts)
    redirect_filter = (QRScanEvent.result_type == "redirect")
    total_scans = db.query(func.count(QRScanEvent.id)).filter(redirect_filter).scalar() or 0
    scans_today = db.query(func.count(QRScanEvent.id)).filter(
        redirect_filter,
        QRScanEvent.scanned_at >= today_start
    ).scalar() or 0
    scans_week = db.query(func.count(QRScanEvent.id)).filter(
        redirect_filter,
        QRScanEvent.scanned_at >= week_start
    ).scalar() or 0
    scans_month = db.query(func.count(QRScanEvent.id)).filter(
        redirect_filter,
        QRScanEvent.scanned_at >= month_start
    ).scalar() or 0
    
    return {
        "total_qr_codes": total,
        "unassigned": unassigned,
        "active": active,
        "disabled": disabled,
        "retired": retired,
        "total_scans": total_scans,
        "scans_today": scans_today,
        "scans_this_week": scans_week,
        "scans_this_month": scans_month,
    }


def get_scan_events(
    db: Session,
    page: int = 1,
    per_page: int = 50,
    qr_code_id: int = None,
    result_type: str = None,
) -> dict:
    """Get paginated scan events."""
    query = db.query(QRScanEvent)
    
    if qr_code_id:
        query = query.filter(QRScanEvent.qr_code_id == qr_code_id)
    if result_type:
        query = query.filter(QRScanEvent.result_type == result_type)
    
    total = query.count()
    items = query.order_by(QRScanEvent.scanned_at.desc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()
    
    # Enrich with QR ID
    result_items = []
    for item in items:
        qr = db.query(QRCode).filter(QRCode.id == item.qr_code_id).first()
        result_items.append({
            "id": item.id,
            "qr_code_id": item.qr_code_id,
            "qr_id": qr.qr_id if qr else None,
            "scanned_at": item.scanned_at,
            "result_type": item.result_type,
        })
    
    return {
        "items": result_items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }
