from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user, get_admin_user
from app.models import User
from app.schemas import (
    ClientListResponse, ClientDetailResponse, ClientBulkActionRequest,
    ClientBulkActionResponse, ClientSummaryCardResponse, ClientAnalyticsResponse
)
from app.services import client_service

router = APIRouter(prefix="/api/clients", tags=["Client QR Management"])


@router.get("/overview", response_model=ClientSummaryCardResponse)
async def get_clients_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get high-level summary metrics across all clients."""
    return client_service.get_clients_overview_summary(db)


@router.get("", response_model=ClientListResponse)
async def list_clients(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    sort_by: str = Query("client_name", pattern="^(client_name|total_qr_codes|active_qr_codes|total_scans|last_scanned_at)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all clients with their QR inventory and scan usage metrics."""
    return client_service.get_clients_list(
        db, page=page, per_page=per_page,
        search=search, sort_by=sort_by, sort_dir=sort_dir,
    )


@router.get("/{client_name}", response_model=ClientDetailResponse)
async def get_client_detail(
    client_name: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status_filter: Optional[str] = Query(None, pattern="^(all|active|disabled|retired|never_scanned|not_used_30d|recently_used)$"),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get detailed QR inventory and usage metrics for an individual client."""
    return client_service.get_client_details(
        db, client_name=client_name, page=page,
        per_page=per_page, status_filter=status_filter, search=search,
    )


@router.get("/{client_name}/analytics", response_model=ClientAnalyticsResponse)
async def get_client_analytics(
    client_name: str,
    days: int = Query(30, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get scan activity trends, top/least performing QRs, and declining usage trends for a client."""
    return client_service.get_client_analytics(db, client_name=client_name, days=days)


@router.post("/{client_name}/qr/{qr_id}/activate")
async def activate_client_qr_endpoint(
    client_name: str,
    qr_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Activate a disabled QR code belonging to a client (Admin only)."""
    success, message, qr = client_service.activate_client_qr(
        db, client_name=client_name, qr_id_or_token=qr_id, admin_user=admin
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return {
        "success": True,
        "message": message,
        "qr_id": qr.qr_id,
        "status": qr.status.value,
        "destination_url": qr.current_destination,
    }


@router.post("/{client_name}/qr/{qr_id}/deactivate")
async def deactivate_client_qr_endpoint(
    client_name: str,
    qr_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Deactivate an active QR code belonging to a client (Admin only). Preserves destination URL."""
    success, message, qr = client_service.deactivate_client_qr(
        db, client_name=client_name, qr_id_or_token=qr_id, admin_user=admin
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return {
        "success": True,
        "message": message,
        "qr_id": qr.qr_id,
        "status": qr.status.value,
        "preserved_destination": qr.current_destination,
    }


@router.post("/{client_name}/bulk-deactivate", response_model=ClientBulkActionResponse)
async def bulk_deactivate_endpoint(
    client_name: str,
    body: ClientBulkActionRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Bulk deactivate multiple active QR codes belonging to a client (Admin only)."""
    if not body.confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must set confirmation to true to proceed with bulk deactivation.",
        )
    return client_service.bulk_deactivate_client_qrs(
        db, client_name=client_name, qr_ids=body.qr_ids, admin_user=admin
    )


@router.post("/{client_name}/bulk-activate", response_model=ClientBulkActionResponse)
async def bulk_activate_endpoint(
    client_name: str,
    body: ClientBulkActionRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Bulk activate multiple disabled QR codes belonging to a client (Admin only)."""
    if not body.confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must set confirmation to true to proceed with bulk activation.",
        )
    return client_service.bulk_activate_client_qrs(
        db, client_name=client_name, qr_ids=body.qr_ids, admin_user=admin
    )


@router.post("/{client_name}/deactivate-all", response_model=ClientBulkActionResponse)
async def deactivate_all_endpoint(
    client_name: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Deactivate ALL active QR codes for a client (Admin only)."""
    return client_service.deactivate_all_for_client(
        db, client_name=client_name, admin_user=admin
    )


@router.post("/{client_name}/activate-all", response_model=ClientBulkActionResponse)
async def activate_all_endpoint(
    client_name: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Reactivate ALL disabled QR codes for a client (Admin only)."""
    return client_service.activate_all_for_client(
        db, client_name=client_name, admin_user=admin
    )
