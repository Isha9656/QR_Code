from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.auth import get_current_user
from app.models import User, QRCode, QRStatus
from app.schemas import GlobalSearchResponse, SearchQRResult, SearchClientResult
from app.services.client_service import get_distinct_client_names, _get_client_qr_ids

router = APIRouter(prefix="/api/search", tags=["Global Search"])


@router.get("/global", response_model=GlobalSearchResponse)
async def global_search(
    q: str = Query(..., min_length=1, max_length=100, description="Search term for QR ID, token, client name, or destination URL"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Unified global search across QR inventory and clients.
    Available to both ADMIN and OPERATOR.
    Searches:
    - QR ID (e.g. 'QR-000061')
    - Permanent token
    - Client / business name
    - Destination URL
    """
    clean_q = q.strip()
    if len(clean_q) < 2:
        return GlobalSearchResponse(
            query=clean_q,
            total_matches=0,
            qr_codes=[],
            clients=[],
        )

    search_pattern = f"%{clean_q}%"

    # 1. Search QR Codes
    qr_matches = (
        db.query(QRCode)
        .filter(
            or_(
                QRCode.qr_id.ilike(search_pattern),
                QRCode.token.ilike(search_pattern),
                QRCode.current_business_name.ilike(search_pattern),
                QRCode.current_destination.ilike(search_pattern),
            )
        )
        .order_by(QRCode.id.asc())
        .limit(10)
        .all()
    )

    qr_results = [
        SearchQRResult(
            id=qr.id,
            qr_id=qr.qr_id,
            token=qr.token,
            status=qr.status.value,
            current_business_name=qr.current_business_name,
            current_destination=qr.current_destination,
        )
        for qr in qr_matches
    ]

    # 2. Search Clients
    all_client_names = get_distinct_client_names(db)
    matching_clients = [
        name for name in all_client_names
        if clean_q.lower() in name.lower()
    ][:10]

    client_results = []
    for client_name in matching_clients:
        qr_ids = _get_client_qr_ids(db, client_name)
        active_cnt = (
            db.query(QRCode)
            .filter(QRCode.id.in_(qr_ids), QRCode.status == QRStatus.ACTIVE)
            .count()
            if qr_ids else 0
        )
        client_results.append(
            SearchClientResult(
                client_name=client_name,
                total_qrs=len(qr_ids),
                active_qrs=active_cnt,
            )
        )

    total_matches = len(qr_results) + len(client_results)

    return GlobalSearchResponse(
        query=clean_q,
        total_matches=total_matches,
        qr_codes=qr_results,
        clients=client_results,
    )
