from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models import User
from app.schemas import AnalyticsOverview, ScanListResponse
from app.services.analytics import get_overview, get_scan_events, get_global_scan_analytics

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/overview", response_model=AnalyticsOverview)
async def analytics_overview(
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD (Asia/Kolkata)"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD (Asia/Kolkata)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get analytics overview dashboard data with IST time boundaries."""
    return get_overview(db, start_date=start_date, end_date=end_date)


@router.get("/scans", response_model=ScanListResponse)
async def analytics_scans(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    qr_code_id: Optional[int] = None,
    result_type: Optional[str] = None,
    start_date: Optional[str] = Query(None, description="Filter from YYYY-MM-DD IST"),
    end_date: Optional[str] = Query(None, description="Filter to YYYY-MM-DD IST"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get paginated scan event log with IST timestamps."""
    return get_scan_events(
        db, page=page, per_page=per_page,
        qr_code_id=qr_code_id, result_type=result_type,
        start_date=start_date, end_date=end_date,
    )


@router.get("/trends")
async def analytics_trends(
    days: int = Query(30, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get global scan trends and rankings over time in Asia/Kolkata time."""
    return get_global_scan_analytics(db, days=days)
