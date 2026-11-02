from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models import User
from app.schemas import AnalyticsOverview, ScanListResponse
from app.services.analytics import get_overview, get_scan_events

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/overview", response_model=AnalyticsOverview)
async def analytics_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get analytics overview dashboard data."""
    return get_overview(db)


@router.get("/scans", response_model=ScanListResponse)
async def analytics_scans(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    qr_code_id: int = None,
    result_type: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get paginated scan event log."""
    return get_scan_events(
        db, page=page, per_page=per_page,
        qr_code_id=qr_code_id, result_type=result_type,
    )
