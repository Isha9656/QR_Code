import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_, and_, case, select
from app.models import QRCode, QRAssignment, QRScanEvent, QRStatus, AuditLog, User


def get_distinct_client_names(db: Session) -> List[str]:
    """Retrieve all unique client/business names across active, disabled, and past assignments."""
    # From current_business_name
    curr_names = [
        r[0] for r in db.query(QRCode.current_business_name)
        .filter(QRCode.current_business_name.isnot(None), QRCode.current_business_name != "")
        .distinct().all()
    ]
    # From historical assignments
    hist_names = [
        r[0] for r in db.query(QRAssignment.business_name)
        .filter(QRAssignment.business_name.isnot(None), QRAssignment.business_name != "")
        .distinct().all()
    ]
    all_names = sorted(list(set(curr_names + hist_names)))
    return [name for name in all_names if name]


def _get_client_qr_ids(db: Session, client_name: str) -> List[int]:
    """Get internal database IDs of all QR codes associated with a client."""
    # QRs whose current business matches
    direct_qr_ids = [
        r[0] for r in db.query(QRCode.id)
        .filter(func.lower(QRCode.current_business_name) == client_name.lower())
        .all()
    ]
    
    # QRs whose most recent assignment was for this client (useful if retired or current was unset)
    latest_assign_subq = (
        db.query(
            QRAssignment.qr_code_id,
            func.max(QRAssignment.assigned_at).label("max_assigned_at")
        )
        .group_by(QRAssignment.qr_code_id)
        .subquery()
    )
    
    hist_qr_ids = [
        r[0] for r in db.query(QRAssignment.qr_code_id)
        .join(
            latest_assign_subq,
            and_(
                QRAssignment.qr_code_id == latest_assign_subq.c.qr_code_id,
                QRAssignment.assigned_at == latest_assign_subq.c.max_assigned_at,
            )
        )
        .filter(func.lower(QRAssignment.business_name) == client_name.lower())
        .all()
    ]
    
    return sorted(list(set(direct_qr_ids + hist_qr_ids)))


def get_clients_overview_summary(db: Session) -> Dict[str, Any]:
    """Calculate dashboard summary cards across all clients."""
    client_names = get_distinct_client_names(db)
    total_clients = len(client_names)
    
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)
    
    # Assigned QR codes (exclude unassigned)
    assigned_qrs = db.query(QRCode).filter(QRCode.status != QRStatus.UNASSIGNED).all()
    total_qr_codes = len(assigned_qrs)
    active_count = sum(1 for q in assigned_qrs if q.status == QRStatus.ACTIVE)
    disabled_count = sum(1 for q in assigned_qrs if q.status == QRStatus.DISABLED)
    retired_count = sum(1 for q in assigned_qrs if q.status == QRStatus.RETIRED)
    
    # Subquery for QRs that had scans in the last 30 days
    recent_scans_subq = (
        db.query(QRScanEvent.qr_code_id)
        .filter(
            QRScanEvent.result_type == "redirect",
            QRScanEvent.scanned_at >= thirty_days_ago,
        )
        .distinct()
        .subquery()
    )
    
    # Active or Disabled QRs that have NO scan in the last 30 days
    no_recent_usage_count = (
        db.query(func.count(QRCode.id))
        .filter(
            QRCode.status.in_([QRStatus.ACTIVE, QRStatus.DISABLED]),
            ~QRCode.id.in_(select(recent_scans_subq.c.qr_code_id)),
        )
        .scalar() or 0
    )
    
    return {
        "total_clients": total_clients,
        "total_qr_codes": total_qr_codes,
        "active_qr_codes": active_count,
        "disabled_qr_codes": disabled_count,
        "retired_qr_codes": retired_count,
        "qr_codes_without_recent_usage": no_recent_usage_count,
    }


def get_clients_list(
    db: Session,
    page: int = 1,
    per_page: int = 20,
    search: Optional[str] = None,
    sort_by: str = "client_name",
    sort_dir: str = "asc",
) -> Dict[str, Any]:
    """Get paginated, searchable, sortable list of all clients with usage and lifecycle metrics."""
    client_names = get_distinct_client_names(db)
    
    if search:
        s = search.strip().lower()
        client_names = [c for c in client_names if s in c.lower()]
    
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)
    
    client_records = []
    
    for client in client_names:
        qr_ids = _get_client_qr_ids(db, client)
        if not qr_ids:
            continue
        
        qrs = db.query(QRCode).filter(QRCode.id.in_(qr_ids)).all()
        total_qrs = len(qrs)
        active_cnt = sum(1 for q in qrs if q.status == QRStatus.ACTIVE)
        disabled_cnt = sum(1 for q in qrs if q.status == QRStatus.DISABLED)
        retired_cnt = sum(1 for q in qrs if q.status == QRStatus.RETIRED)
        
        # Scans for this client's QR codes
        scan_stats = (
            db.query(
                func.count(QRScanEvent.id).label("total_scans"),
                func.max(QRScanEvent.scanned_at).label("last_scanned_at"),
            )
            .filter(
                QRScanEvent.qr_code_id.in_(qr_ids),
                QRScanEvent.result_type == "redirect",
            )
            .first()
        )
        total_scans = scan_stats[0] if scan_stats and scan_stats[0] else 0
        last_scanned_at = scan_stats[1] if scan_stats else None
        
        # QRs with scans
        scanned_qr_ids_set = set(
            r[0] for r in db.query(QRScanEvent.qr_code_id)
            .filter(
                QRScanEvent.qr_code_id.in_(qr_ids),
                QRScanEvent.result_type == "redirect",
            )
            .distinct()
            .all()
        )
        never_scanned_cnt = sum(1 for q in qrs if q.id not in scanned_qr_ids_set)
        
        # QRs with recent scans (last 30d)
        recent_scanned_qr_ids_set = set(
            r[0] for r in db.query(QRScanEvent.qr_code_id)
            .filter(
                QRScanEvent.qr_code_id.in_(qr_ids),
                QRScanEvent.result_type == "redirect",
                QRScanEvent.scanned_at >= thirty_days_ago,
            )
            .distinct()
            .all()
        )
        not_scanned_30d_cnt = sum(
            1 for q in qrs
            if q.status in [QRStatus.ACTIVE, QRStatus.DISABLED] and q.id not in recent_scanned_qr_ids_set
        )
        
        client_records.append({
            "client_name": client,
            "total_qr_codes": total_qrs,
            "active_qr_codes": active_cnt,
            "disabled_qr_codes": disabled_cnt,
            "retired_qr_codes": retired_cnt,
            "total_scans": total_scans,
            "last_scanned_at": last_scanned_at,
            "never_scanned_count": never_scanned_cnt,
            "not_scanned_30d_count": not_scanned_30d_cnt,
        })
    
    # Sorting
    reverse = (sort_dir.lower() == "desc")
    if sort_by == "total_qr_codes":
        client_records.sort(key=lambda x: x["total_qr_codes"], reverse=reverse)
    elif sort_by == "active_qr_codes":
        client_records.sort(key=lambda x: x["active_qr_codes"], reverse=reverse)
    elif sort_by == "total_scans":
        client_records.sort(key=lambda x: x["total_scans"], reverse=reverse)
    elif sort_by == "last_scanned_at":
        client_records.sort(key=lambda x: x["last_scanned_at"] or datetime.min, reverse=reverse)
    else:
        client_records.sort(key=lambda x: x["client_name"].lower(), reverse=reverse)
    
    total = len(client_records)
    total_pages = max(1, (total + per_page - 1) // per_page)
    offset = (page - 1) * per_page
    paged_items = client_records[offset: offset + per_page]
    
    summary = get_clients_overview_summary(db)
    
    return {
        "items": paged_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "summary": summary,
    }


def get_client_details(
    db: Session,
    client_name: str,
    page: int = 1,
    per_page: int = 25,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve detailed client inventory, QR codes, scan statistics, and filter options."""
    qr_ids = _get_client_qr_ids(db, client_name)
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)
    
    if not qr_ids:
        # Check if client exists but has no QRs currently
        return {
            "client_name": client_name,
            "total_qr_codes": 0,
            "active_qr_codes": 0,
            "disabled_qr_codes": 0,
            "retired_qr_codes": 0,
            "total_scans": 0,
            "scans_7d": 0,
            "scans_30d": 0,
            "last_scanned_at": None,
            "never_scanned_count": 0,
            "not_scanned_30d_count": 0,
            "items": [],
            "total": 0,
            "page": page,
            "per_page": per_page,
            "total_pages": 1,
        }
    
    qrs = db.query(QRCode).filter(QRCode.id.in_(qr_ids)).all()
    
    # Pre-calculate scans per QR code
    scan_rows = (
        db.query(
            QRScanEvent.qr_code_id,
            func.count(QRScanEvent.id).label("total_scans"),
            func.max(QRScanEvent.scanned_at).label("last_scanned_at"),
            func.sum(case((QRScanEvent.scanned_at >= seven_days_ago, 1), else_=0)).label("scans_7d"),
            func.sum(case((QRScanEvent.scanned_at >= thirty_days_ago, 1), else_=0)).label("scans_30d"),
        )
        .filter(
            QRScanEvent.qr_code_id.in_(qr_ids),
            QRScanEvent.result_type == "redirect",
        )
        .group_by(QRScanEvent.qr_code_id)
        .all()
    )
    
    scan_map = {
        row.qr_code_id: {
            "total_scans": row.total_scans or 0,
            "last_scanned_at": row.last_scanned_at,
            "scans_7d": int(row.scans_7d or 0),
            "scans_30d": int(row.scans_30d or 0),
        }
        for row in scan_rows
    }
    
    items = []
    client_total_scans = 0
    client_scans_7d = 0
    client_scans_30d = 0
    client_last_scanned_at = None
    never_scanned_count = 0
    not_scanned_30d_count = 0
    
    for qr in qrs:
        s = scan_map.get(qr.id, {
            "total_scans": 0,
            "last_scanned_at": None,
            "scans_7d": 0,
            "scans_30d": 0,
        })
        
        client_total_scans += s["total_scans"]
        client_scans_7d += s["scans_7d"]
        client_scans_30d += s["scans_30d"]
        if s["last_scanned_at"]:
            if not client_last_scanned_at or s["last_scanned_at"] > client_last_scanned_at:
                client_last_scanned_at = s["last_scanned_at"]
        
        is_never = (s["total_scans"] == 0)
        is_not_30d = (
            qr.status in [QRStatus.ACTIVE, QRStatus.DISABLED] and
            (s["last_scanned_at"] is None or s["last_scanned_at"] < thirty_days_ago)
        )
        
        if is_never:
            never_scanned_count += 1
        if is_not_30d:
            not_scanned_30d_count += 1
        
        # Destination resolution
        dest = qr.current_destination
        if not dest and qr.assignments:
            dest = qr.assignments[0].destination_url
        
        items.append({
            "id": qr.id,
            "qr_id": qr.qr_id,
            "token": qr.token,
            "client_name": client_name,
            "destination_url": dest,
            "status": qr.status.value,
            "total_scans": s["total_scans"],
            "scans_7d": s["scans_7d"],
            "scans_30d": s["scans_30d"],
            "last_scanned_at": s["last_scanned_at"],
            "created_at": qr.created_at,
            "last_status_change": qr.updated_at or qr.created_at,
            "is_never_scanned": is_never,
            "is_not_used_30d": is_not_30d,
        })
    
    total_qrs = len(qrs)
    active_cnt = sum(1 for q in qrs if q.status == QRStatus.ACTIVE)
    disabled_cnt = sum(1 for q in qrs if q.status == QRStatus.DISABLED)
    retired_cnt = sum(1 for q in qrs if q.status == QRStatus.RETIRED)
    
    # Filter
    filtered_items = items
    if status_filter and status_filter.lower() != "all":
        fl = status_filter.lower()
        if fl == "active":
            filtered_items = [i for i in filtered_items if i["status"] == "active"]
        elif fl == "disabled":
            filtered_items = [i for i in filtered_items if i["status"] == "disabled"]
        elif fl == "retired":
            filtered_items = [i for i in filtered_items if i["status"] == "retired"]
        elif fl == "never_scanned":
            filtered_items = [i for i in filtered_items if i["is_never_scanned"]]
        elif fl == "not_used_30d":
            filtered_items = [i for i in filtered_items if i["is_not_used_30d"]]
        elif fl == "recently_used":
            filtered_items = [i for i in filtered_items if i["scans_30d"] > 0]
    
    if search:
        sq = search.strip().lower()
        filtered_items = [
            i for i in filtered_items
            if sq in i["qr_id"].lower() or sq in i["token"].lower() or (i["destination_url"] and sq in i["destination_url"].lower())
        ]
    
    # Sort default: status active first, then most scanned, then ID desc
    filtered_items.sort(key=lambda x: (
        0 if x["status"] == "active" else 1 if x["status"] == "disabled" else 2,
        -x["total_scans"],
        -x["id"],
    ))
    
    total_filtered = len(filtered_items)
    total_pages = max(1, (total_filtered + per_page - 1) // per_page)
    offset = (page - 1) * per_page
    paged_items = filtered_items[offset: offset + per_page]
    
    return {
        "client_name": client_name,
        "total_qr_codes": total_qrs,
        "active_qr_codes": active_cnt,
        "disabled_qr_codes": disabled_cnt,
        "retired_qr_codes": retired_cnt,
        "total_scans": client_total_scans,
        "scans_7d": client_scans_7d,
        "scans_30d": client_scans_30d,
        "last_scanned_at": client_last_scanned_at,
        "never_scanned_count": never_scanned_count,
        "not_scanned_30d_count": not_scanned_30d_count,
        "items": paged_items,
        "total": total_filtered,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


def activate_client_qr(
    db: Session,
    client_name: str,
    qr_id_or_token: str,
    admin_user: User,
) -> Tuple[bool, str, Optional[QRCode]]:
    """Activate a single disabled QR code belonging to client."""
    qr = db.query(QRCode).filter(
        or_(QRCode.qr_id == qr_id_or_token, QRCode.token == qr_id_or_token)
    ).first()
    
    if not qr:
        return False, "QR code not found", None
    
    # Ownership verification
    qr_ids_for_client = _get_client_qr_ids(db, client_name)
    if qr.id not in qr_ids_for_client:
        return False, f"QR code {qr.qr_id} does not belong to client '{client_name}'", qr
    
    # Retirement terminal check
    if qr.status == QRStatus.RETIRED:
        return False, "Retired QR codes cannot be activated. Retirement is permanent and terminal.", qr
    
    if qr.status == QRStatus.ACTIVE:
        return False, f"QR code {qr.qr_id} is already active", qr
    
    if qr.status == QRStatus.UNASSIGNED:
        return False, f"QR code {qr.qr_id} is unassigned. Assign it to a destination first.", qr
    
    prev_status = qr.status.value
    qr.status = QRStatus.ACTIVE
    
    audit = AuditLog(
        user_id=admin_user.id,
        action="client_qr_activate",
        entity_type="qr_code",
        entity_id=qr.id,
        status="success",
        details=json.dumps({
            "qr_id": qr.qr_id,
            "client_name": client_name,
            "previous_status": prev_status,
            "new_status": qr.status.value,
            "destination_url": qr.current_destination,
        }),
    )
    db.add(audit)
    db.commit()
    return True, f"QR code {qr.qr_id} activated successfully", qr


def deactivate_client_qr(
    db: Session,
    client_name: str,
    qr_id_or_token: str,
    admin_user: User,
) -> Tuple[bool, str, Optional[QRCode]]:
    """Deactivate an active QR code belonging to client (preserves destination & token)."""
    qr = db.query(QRCode).filter(
        or_(QRCode.qr_id == qr_id_or_token, QRCode.token == qr_id_or_token)
    ).first()
    
    if not qr:
        return False, "QR code not found", None
    
    # Ownership verification
    qr_ids_for_client = _get_client_qr_ids(db, client_name)
    if qr.id not in qr_ids_for_client:
        return False, f"QR code {qr.qr_id} does not belong to client '{client_name}'", qr
    
    # Retirement terminal check
    if qr.status == QRStatus.RETIRED:
        return False, "Cannot deactivate a retired QR code. Retirement is permanent and terminal.", qr
    
    if qr.status == QRStatus.DISABLED:
        return False, f"QR code {qr.qr_id} is already disabled", qr
    
    if qr.status == QRStatus.UNASSIGNED:
        return False, f"Cannot deactivate unassigned QR code {qr.qr_id}", qr
    
    prev_status = qr.status.value
    qr.status = QRStatus.DISABLED
    
    audit = AuditLog(
        user_id=admin_user.id,
        action="client_qr_deactivate",
        entity_type="qr_code",
        entity_id=qr.id,
        status="success",
        details=json.dumps({
            "qr_id": qr.qr_id,
            "client_name": client_name,
            "previous_status": prev_status,
            "new_status": qr.status.value,
            "preserved_destination": qr.current_destination,
        }),
    )
    db.add(audit)
    db.commit()
    return True, f"QR code {qr.qr_id} deactivated successfully (destination preserved)", qr


def bulk_deactivate_client_qrs(
    db: Session,
    client_name: str,
    qr_ids: List[str],
    admin_user: User,
) -> Dict[str, Any]:
    """Bulk deactivate multiple active QR codes belonging to client."""
    client_qr_ids = _get_client_qr_ids(db, client_name)
    bulk_ref = f"bulk-deact-{uuid.uuid4().hex[:8]}"
    
    affected_ids = []
    skipped_count = 0
    
    for q_id_str in qr_ids:
        qr = db.query(QRCode).filter(
            or_(QRCode.qr_id == q_id_str, QRCode.token == q_id_str)
        ).first()
        
        # Verify ownership, active status, not retired
        if not qr or qr.id not in client_qr_ids:
            skipped_count += 1
            continue
        if qr.status == QRStatus.RETIRED or qr.status != QRStatus.ACTIVE:
            skipped_count += 1
            continue
        
        prev_status = qr.status.value
        qr.status = QRStatus.DISABLED
        affected_ids.append(qr.qr_id)
        
        audit = AuditLog(
            user_id=admin_user.id,
            action="client_qr_deactivate",
            entity_type="qr_code",
            entity_id=qr.id,
            status="success",
            details=json.dumps({
                "qr_id": qr.qr_id,
                "client_name": client_name,
                "previous_status": prev_status,
                "new_status": qr.status.value,
                "bulk_reference": bulk_ref,
            }),
        )
        db.add(audit)
    
    if affected_ids:
        db.commit()
    
    return {
        "client_name": client_name,
        "action": "bulk_deactivate",
        "requested_count": len(qr_ids),
        "affected_count": len(affected_ids),
        "affected_qr_ids": affected_ids,
        "skipped_count": skipped_count,
        "message": f"Successfully deactivated {len(affected_ids)} QR code(s). {skipped_count} skipped.",
    }


def bulk_activate_client_qrs(
    db: Session,
    client_name: str,
    qr_ids: List[str],
    admin_user: User,
) -> Dict[str, Any]:
    """Bulk activate multiple disabled QR codes belonging to client."""
    client_qr_ids = _get_client_qr_ids(db, client_name)
    bulk_ref = f"bulk-act-{uuid.uuid4().hex[:8]}"
    
    affected_ids = []
    skipped_count = 0
    
    for q_id_str in qr_ids:
        qr = db.query(QRCode).filter(
            or_(QRCode.qr_id == q_id_str, QRCode.token == q_id_str)
        ).first()
        
        # Verify ownership, disabled status, not retired
        if not qr or qr.id not in client_qr_ids:
            skipped_count += 1
            continue
        if qr.status == QRStatus.RETIRED or qr.status != QRStatus.DISABLED:
            skipped_count += 1
            continue
        
        prev_status = qr.status.value
        qr.status = QRStatus.ACTIVE
        affected_ids.append(qr.qr_id)
        
        audit = AuditLog(
            user_id=admin_user.id,
            action="client_qr_activate",
            entity_type="qr_code",
            entity_id=qr.id,
            status="success",
            details=json.dumps({
                "qr_id": qr.qr_id,
                "client_name": client_name,
                "previous_status": prev_status,
                "new_status": qr.status.value,
                "bulk_reference": bulk_ref,
            }),
        )
        db.add(audit)
    
    if affected_ids:
        db.commit()
    
    return {
        "client_name": client_name,
        "action": "bulk_activate",
        "requested_count": len(qr_ids),
        "affected_count": len(affected_ids),
        "affected_qr_ids": affected_ids,
        "skipped_count": skipped_count,
        "message": f"Successfully activated {len(affected_ids)} QR code(s). {skipped_count} skipped.",
    }


def deactivate_all_for_client(
    db: Session,
    client_name: str,
    admin_user: User,
) -> Dict[str, Any]:
    """Deactivate ALL active QR codes belonging to a selected client."""
    client_qr_ids = _get_client_qr_ids(db, client_name)
    active_qrs = db.query(QRCode).filter(
        QRCode.id.in_(client_qr_ids),
        QRCode.status == QRStatus.ACTIVE,
    ).all()
    
    active_ids = [q.qr_id for q in active_qrs]
    return bulk_deactivate_client_qrs(db, client_name, active_ids, admin_user)


def activate_all_for_client(
    db: Session,
    client_name: str,
    admin_user: User,
) -> Dict[str, Any]:
    """Reactivate ALL disabled QR codes belonging to a selected client."""
    client_qr_ids = _get_client_qr_ids(db, client_name)
    disabled_qrs = db.query(QRCode).filter(
        QRCode.id.in_(client_qr_ids),
        QRCode.status == QRStatus.DISABLED,
    ).all()
    
    disabled_ids = [q.qr_id for q in disabled_qrs]
    return bulk_activate_client_qrs(db, client_name, disabled_ids, admin_user)


def get_client_analytics(
    db: Session,
    client_name: str,
    days: int = 30,
) -> Dict[str, Any]:
    """
    Generate client-level scan usage analytics:
    - Daily scan activity
    - Weekly scan activity
    - Monthly scan activity
    - Most-used QR codes
    - Least-used QR codes
    - QR codes with no scans
    - QR codes with declining usage (last 14d vs prior 14d)
    """
    days = max(7, min(days, 365))
    qr_ids = _get_client_qr_ids(db, client_name)
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)
    
    if not qr_ids:
        return {
            "client_name": client_name,
            "date_range_days": days,
            "daily_scans": [],
            "weekly_scans": [],
            "monthly_scans": [],
            "most_used_qrs": [],
            "least_used_qrs": [],
            "no_scan_qrs": [],
            "declining_qrs": [],
        }
    
    # 1. Daily scan activity
    daily_rows = (
        db.query(
            func.strftime("%Y-%m-%d", QRScanEvent.scanned_at).label("day"),
            func.count(QRScanEvent.id).label("scans"),
        )
        .filter(
            QRScanEvent.qr_code_id.in_(qr_ids),
            QRScanEvent.result_type == "redirect",
            QRScanEvent.scanned_at >= start_date,
        )
        .group_by("day")
        .order_by("day")
        .all()
    )
    daily_map = {r.day: r.scans for r in daily_rows}
    
    # Generate complete sequence for days
    daily_scans = []
    for d in range(days):
        dt = (now - timedelta(days=days - 1 - d)).strftime("%Y-%m-%d")
        daily_scans.append({
            "date": dt,
            "scans": daily_map.get(dt, 0),
        })
    
    # 2. Weekly scan activity
    weekly_rows = (
        db.query(
            func.strftime("%Y-W%W", QRScanEvent.scanned_at).label("week"),
            func.count(QRScanEvent.id).label("scans"),
        )
        .filter(
            QRScanEvent.qr_code_id.in_(qr_ids),
            QRScanEvent.result_type == "redirect",
            QRScanEvent.scanned_at >= (now - timedelta(days=180)),
        )
        .group_by("week")
        .order_by("week")
        .all()
    )
    weekly_scans = [{"week": r.week, "scans": r.scans} for r in weekly_rows]
    
    # 3. Monthly scan activity
    monthly_rows = (
        db.query(
            func.strftime("%Y-%m", QRScanEvent.scanned_at).label("month"),
            func.count(QRScanEvent.id).label("scans"),
        )
        .filter(
            QRScanEvent.qr_code_id.in_(qr_ids),
            QRScanEvent.result_type == "redirect",
            QRScanEvent.scanned_at >= (now - timedelta(days=365)),
        )
        .group_by("month")
        .order_by("month")
        .all()
    )
    monthly_scans = [{"month": r.month, "scans": r.scans} for r in monthly_rows]
    
    # 4. QR-level metrics for ranking
    all_client_qrs = db.query(QRCode).filter(QRCode.id.in_(qr_ids)).all()
    
    qr_scans_summary = (
        db.query(
            QRScanEvent.qr_code_id,
            func.count(QRScanEvent.id).label("total_scans"),
            func.sum(case((QRScanEvent.scanned_at >= (now - timedelta(days=14)), 1), else_=0)).label("last_14d"),
            func.sum(case((and_(
                QRScanEvent.scanned_at >= (now - timedelta(days=28)),
                QRScanEvent.scanned_at < (now - timedelta(days=14)),
            ), 1), else_=0)).label("prior_14d"),
        )
        .filter(
            QRScanEvent.qr_code_id.in_(qr_ids),
            QRScanEvent.result_type == "redirect",
        )
        .group_by(QRScanEvent.qr_code_id)
        .all()
    )
    
    summary_map = {
        r.qr_code_id: {
            "total_scans": r.total_scans or 0,
            "last_14d": int(r.last_14d or 0),
            "prior_14d": int(r.prior_14d or 0),
        }
        for r in qr_scans_summary
    }
    
    enriched_qrs = []
    for qr in all_client_qrs:
        s = summary_map.get(qr.id, {"total_scans": 0, "last_14d": 0, "prior_14d": 0})
        dest = qr.current_destination
        if not dest and qr.assignments:
            dest = qr.assignments[0].destination_url
        
        enriched_qrs.append({
            "qr_id": qr.qr_id,
            "status": qr.status.value,
            "destination_url": dest or "No destination",
            "total_scans": s["total_scans"],
            "last_14d": s["last_14d"],
            "prior_14d": s["prior_14d"],
        })
    
    # Most used
    most_used = sorted(
        [q for q in enriched_qrs if q["total_scans"] > 0],
        key=lambda x: -x["total_scans"],
    )[:5]
    
    # Least used (> 0 scans)
    least_used = sorted(
        [q for q in enriched_qrs if q["total_scans"] > 0],
        key=lambda x: x["total_scans"],
    )[:5]
    
    # No scan QRs
    no_scans = [q for q in enriched_qrs if q["total_scans"] == 0]
    
    # Declining QRs (prior 14d had at least 4 scans, and recent 14d is down by 50% or more)
    declining = []
    for q in enriched_qrs:
        prior = q["prior_14d"]
        recent = q["last_14d"]
        if prior >= 4 and recent <= (prior * 0.5):
            pct_drop = round(((prior - recent) / prior) * 100, 1)
            declining.append({
                "qr_id": q["qr_id"],
                "destination_url": q["destination_url"],
                "status": q["status"],
                "recent_14d_scans": recent,
                "prior_14d_scans": prior,
                "drop_percentage": pct_drop,
            })
    declining.sort(key=lambda x: -x["drop_percentage"])
    
    return {
        "client_name": client_name,
        "date_range_days": days,
        "daily_scans": daily_scans,
        "weekly_scans": weekly_scans,
        "monthly_scans": monthly_scans,
        "most_used_qrs": most_used,
        "least_used_qrs": least_used,
        "no_scan_qrs": no_scans,
        "declining_qrs": declining,
    }
