from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.models import QRCode, QRScanEvent, QRStatus, QRAssignment
from app.core.timezone import (
    get_ist_today_bounds_in_utc,
    get_ist_yesterday_bounds_in_utc,
    get_ist_week_bounds_in_utc,
    get_ist_month_bounds_in_utc,
    get_ist_day_bounds_in_utc,
    to_ist_date_str,
    to_ist_str,
    to_ist,
    ist_now,
)
from app.services.client_service import get_distinct_client_names, _attribute_scan_to_client


def get_overview(
    db: Session,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """
    Get comprehensive analytics overview statistics using Asia/Kolkata (IST) calendar boundaries.
    
    All scan metrics represent genuine public redirects, strictly excluding internal previews,
    unassigned attempts, and disabled/retired attempts.
    """
    # 1. QR Inventory lifecycle status counts
    total = db.query(func.count(QRCode.id)).scalar() or 0
    unassigned = db.query(func.count(QRCode.id)).filter(QRCode.status == QRStatus.UNASSIGNED).scalar() or 0
    active = db.query(func.count(QRCode.id)).filter(QRCode.status == QRStatus.ACTIVE).scalar() or 0
    disabled = db.query(func.count(QRCode.id)).filter(QRCode.status == QRStatus.DISABLED).scalar() or 0
    retired = db.query(func.count(QRCode.id)).filter(QRCode.status == QRStatus.RETIRED).scalar() or 0
    assigned = total - unassigned

    # 2. Genuine public redirects filter
    redirect_filter = (QRScanEvent.result_type == "redirect")
    total_scans = db.query(func.count(QRScanEvent.id)).filter(redirect_filter).scalar() or 0

    # 3. Exact Asia/Kolkata (IST) calendar boundaries mapped to UTC intervals
    today_start_utc, today_end_utc = get_ist_today_bounds_in_utc()
    yesterday_start_utc, yesterday_end_utc = get_ist_yesterday_bounds_in_utc()
    week_start_utc, week_end_utc = get_ist_week_bounds_in_utc()
    month_start_utc, month_end_utc = get_ist_month_bounds_in_utc()

    scans_today = db.query(func.count(QRScanEvent.id)).filter(
        redirect_filter,
        QRScanEvent.scanned_at >= today_start_utc,
        QRScanEvent.scanned_at <= today_end_utc,
    ).scalar() or 0

    scans_yesterday = db.query(func.count(QRScanEvent.id)).filter(
        redirect_filter,
        QRScanEvent.scanned_at >= yesterday_start_utc,
        QRScanEvent.scanned_at <= yesterday_end_utc,
    ).scalar() or 0

    scans_week = db.query(func.count(QRScanEvent.id)).filter(
        redirect_filter,
        QRScanEvent.scanned_at >= week_start_utc,
        QRScanEvent.scanned_at <= week_end_utc,
    ).scalar() or 0

    scans_month = db.query(func.count(QRScanEvent.id)).filter(
        redirect_filter,
        QRScanEvent.scanned_at >= month_start_utc,
        QRScanEvent.scanned_at <= month_end_utc,
    ).scalar() or 0

    # 4. Optional custom date range filter in IST
    custom_scans = None
    if start_date and end_date:
        try:
            c_start_utc, _ = get_ist_day_bounds_in_utc(start_date)
            _, c_end_utc = get_ist_day_bounds_in_utc(end_date)
            custom_scans = db.query(func.count(QRScanEvent.id)).filter(
                redirect_filter,
                QRScanEvent.scanned_at >= c_start_utc,
                QRScanEvent.scanned_at <= c_end_utc,
            ).scalar() or 0
        except Exception:
            custom_scans = None

    # 5. QR Scan activity metrics: never scanned & no scans in 30 days
    # Subquery of all QR codes with at least one redirect scan
    scanned_qr_subq = db.query(QRScanEvent.qr_code_id).filter(redirect_filter).distinct().subquery()
    
    # Active QR codes that have never been scanned
    never_scanned_count = db.query(func.count(QRCode.id)).filter(
        QRCode.status == QRStatus.ACTIVE,
        ~QRCode.id.in_(scanned_qr_subq)
    ).scalar() or 0

    # Active QR codes not scanned in the last 30 days (in IST)
    thirty_days_ago_utc = (datetime.utcnow() - timedelta(days=30))
    recent_scanned_subq = db.query(QRScanEvent.qr_code_id).filter(
        redirect_filter,
        QRScanEvent.scanned_at >= thirty_days_ago_utc
    ).distinct().subquery()

    not_scanned_30d_count = db.query(func.count(QRCode.id)).filter(
        QRCode.status == QRStatus.ACTIVE,
        ~QRCode.id.in_(recent_scanned_subq)
    ).scalar() or 0

    # Count of businesses
    total_businesses = len(get_distinct_client_names(db))

    return {
        "total_qr_codes": total,
        "unassigned": unassigned,
        "assigned": assigned,
        "active": active,
        "disabled": disabled,
        "retired": retired,
        "total_scans": total_scans,
        "scans_today": scans_today,
        "scans_yesterday": scans_yesterday,
        "scans_this_week": scans_week,
        "scans_this_month": scans_month,
        "custom_range_scans": custom_scans,
        "never_scanned_count": never_scanned_count,
        "not_scanned_30d_count": not_scanned_30d_count,
        "total_businesses": total_businesses,
        "timezone": "Asia/Kolkata",
        "timezone_offset": "+05:30",
    }


def get_scan_events(
    db: Session,
    page: int = 1,
    per_page: int = 50,
    qr_code_id: Optional[int] = None,
    result_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """Get paginated scan events with optional IST date boundary filtering."""
    query = db.query(QRScanEvent)
    
    if qr_code_id:
        query = query.filter(QRScanEvent.qr_code_id == qr_code_id)
    if result_type:
        query = query.filter(QRScanEvent.result_type == result_type)
    
    if start_date:
        try:
            s_utc, _ = get_ist_day_bounds_in_utc(start_date)
            query = query.filter(QRScanEvent.scanned_at >= s_utc)
        except Exception:
            pass
    if end_date:
        try:
            _, e_utc = get_ist_day_bounds_in_utc(end_date)
            query = query.filter(QRScanEvent.scanned_at <= e_utc)
        except Exception:
            pass

    total = query.count()
    items = query.order_by(QRScanEvent.scanned_at.desc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()
    
    result_items = []
    for item in items:
        qr = db.query(QRCode).filter(QRCode.id == item.qr_code_id).first()
        attributed_client = _attribute_scan_to_client(db, item) if item.result_type == "redirect" else None
        result_items.append({
            "id": item.id,
            "qr_code_id": item.qr_code_id,
            "qr_id": qr.qr_id if qr else None,
            "scanned_at": item.scanned_at,
            "scanned_at_ist": to_ist_str(item.scanned_at),
            "result_type": item.result_type,
            "attributed_client": attributed_client,
            "ip_address": item.ip_address,
        })
    
    return {
        "items": result_items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


def get_global_scan_analytics(db: Session, days: int = 30) -> Dict[str, Any]:
    """
    Generate platform-wide global scan trends and rankings in Asia/Kolkata time.
    """
    days = max(7, min(days, 365))
    today_ist = ist_now().date()
    start_date_ist = today_ist - timedelta(days=days - 1)
    start_utc, _ = get_ist_day_bounds_in_utc(start_date_ist)

    # All genuine redirect scans in the requested window
    redirect_filter = (QRScanEvent.result_type == "redirect")
    scans = (
        db.query(QRScanEvent)
        .filter(redirect_filter, QRScanEvent.scanned_at >= start_utc)
        .all()
    )

    # Group daily scans by Asia/Kolkata calendar day
    daily_map: Dict[str, int] = {}
    client_scan_counts: Dict[str, int] = {}
    qr_scan_counts: Dict[str, int] = {}

    for scan in scans:
        day_str = to_ist_date_str(scan.scanned_at)
        daily_map[day_str] = daily_map.get(day_str, 0) + 1
        
        # QR count
        qr = db.query(QRCode).filter(QRCode.id == scan.qr_code_id).first()
        qr_key = qr.qr_id if qr else f"ID-{scan.qr_code_id}"
        qr_scan_counts[qr_key] = qr_scan_counts.get(qr_key, 0) + 1

        # Client count using historical attribution
        client_name = _attribute_scan_to_client(db, scan)
        if client_name:
            client_scan_counts[client_name] = client_scan_counts.get(client_name, 0) + 1

    daily_trend = []
    for d in range(days):
        current_d = start_date_ist + timedelta(days=d)
        d_str = current_d.strftime("%Y-%m-%d")
        daily_trend.append({
            "date": d_str,
            "scans": daily_map.get(d_str, 0),
        })

    # Top businesses
    top_businesses = [
        {"business_name": k, "scans": v}
        for k, v in sorted(client_scan_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    ]

    # Top QR codes
    top_qrs = [
        {"qr_id": k, "scans": v}
        for k, v in sorted(qr_scan_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    ]

    return {
        "days": days,
        "daily_trend": daily_trend,
        "top_businesses": top_businesses,
        "top_qrs": top_qrs,
        "total_scans_in_period": len(scans),
        "timezone": "Asia/Kolkata",
    }


def get_single_qr_analytics(db: Session, qr: QRCode, days: int = 30) -> Dict[str, Any]:
    """Get comprehensive scan metrics and daily timeline for a single QR code in Asia/Kolkata time."""
    from app.services.client_service import _attribute_scan_to_client

    # All redirect scans for this QR
    all_redirect_scans = (
        db.query(QRScanEvent)
        .filter(QRScanEvent.qr_code_id == qr.id, QRScanEvent.result_type == "redirect")
        .order_by(QRScanEvent.scanned_at.asc())
        .all()
    )

    total_scans = len(all_redirect_scans)

    today_start_utc, today_end_utc = get_ist_today_bounds_in_utc()
    yesterday_start_utc, yesterday_end_utc = get_ist_yesterday_bounds_in_utc()
    now_utc = datetime.utcnow()
    seven_days_ago = now_utc - timedelta(days=7)
    thirty_days_ago = now_utc - timedelta(days=30)

    scans_today = sum(1 for s in all_redirect_scans if today_start_utc <= s.scanned_at <= today_end_utc)
    scans_yesterday = sum(1 for s in all_redirect_scans if yesterday_start_utc <= s.scanned_at <= yesterday_end_utc)
    scans_7d = sum(1 for s in all_redirect_scans if s.scanned_at >= seven_days_ago)
    scans_30d = sum(1 for s in all_redirect_scans if s.scanned_at >= thirty_days_ago)

    last_scan = all_redirect_scans[-1].scanned_at if all_redirect_scans else None

    # 30-day daily breakdown
    today_ist = ist_now().date()
    start_date_ist = today_ist - timedelta(days=days - 1)
    start_utc, _ = get_ist_day_bounds_in_utc(start_date_ist)

    daily_map: Dict[str, int] = {}
    for scan in all_redirect_scans:
        if scan.scanned_at >= start_utc:
            d_str = to_ist_date_str(scan.scanned_at)
            daily_map[d_str] = daily_map.get(d_str, 0) + 1

    daily_trend = []
    for d in range(days):
        current_d = start_date_ist + timedelta(days=d)
        d_str = current_d.strftime("%Y-%m-%d")
        daily_trend.append({
            "date": d_str,
            "scans": daily_map.get(d_str, 0),
        })

    # Recent scan events (all result types, up to 15 latest)
    recent_events = (
        db.query(QRScanEvent)
        .filter(QRScanEvent.qr_code_id == qr.id)
        .order_by(QRScanEvent.scanned_at.desc())
        .limit(15)
        .all()
    )

    recent_scans = []
    for ev in recent_events:
        attributed_client = _attribute_scan_to_client(db, ev) if ev.result_type == "redirect" else None
        recent_scans.append({
            "id": ev.id,
            "scanned_at": ev.scanned_at,
            "scanned_at_ist": to_ist_str(ev.scanned_at),
            "result_type": ev.result_type,
            "attributed_client": attributed_client,
            "ip_address": ev.ip_address,
            "user_agent": ev.user_agent,
        })

    return {
        "qr_id": qr.qr_id,
        "token": qr.token,
        "status": qr.status.value,
        "current_business_name": qr.current_business_name,
        "current_destination": qr.current_destination,
        "total_scans": total_scans,
        "scans_today": scans_today,
        "scans_yesterday": scans_yesterday,
        "scans_7d": scans_7d,
        "scans_30d": scans_30d,
        "last_scanned_at": last_scan,
        "last_scanned_at_ist": to_ist_str(last_scan) if last_scan else None,
        "daily_trend": daily_trend,
        "recent_scans": recent_scans,
        "timezone": "Asia/Kolkata",
    }
