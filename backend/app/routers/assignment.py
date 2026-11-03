from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.auth import get_current_user, get_admin_user
from app.models import User, UserRole, QRCode, QRAssignment, QRStatus, AuditLog
from app.schemas import (
    AssignRequest, ReassignRequest, AssignmentResponse, AssignmentHistoryResponse
)
from app.config import get_settings
import json

router = APIRouter(prefix="/api/qr", tags=["Assignment"])


def assignment_to_response(assignment: QRAssignment, db: Session) -> AssignmentResponse:
    """Convert an assignment model to response."""
    assigned_user = db.query(User).filter(User.id == assignment.assigned_by).first()
    deactivated_user = None
    if assignment.deactivated_by:
        deactivated_user = db.query(User).filter(User.id == assignment.deactivated_by).first()
    
    return AssignmentResponse(
        id=assignment.id,
        qr_code_id=assignment.qr_code_id,
        business_name=assignment.business_name,
        destination_url=assignment.destination_url,
        notes=assignment.notes,
        is_active=assignment.is_active,
        assigned_by=assignment.assigned_by,
        assigned_by_name=assigned_user.display_name if assigned_user else None,
        assigned_at=assignment.assigned_at,
        deactivated_at=assignment.deactivated_at,
        deactivated_by=assignment.deactivated_by,
        deactivated_by_name=deactivated_user.display_name if deactivated_user else None,
        expiry_date=assignment.expiry_date,
    )


@router.get("/{qr_id_or_db_id}/history", response_model=AssignmentHistoryResponse)
async def get_assignment_history(
    qr_id_or_db_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get full assignment history for a QR code."""
    qr = _resolve_qr(qr_id_or_db_id, db)
    
    assignments = db.query(QRAssignment).filter(
        QRAssignment.qr_code_id == qr.id
    ).order_by(QRAssignment.assigned_at.desc()).all()
    
    return AssignmentHistoryResponse(
        qr_id=qr.qr_id,
        qr_status=qr.status.value,
        assignments=[assignment_to_response(a, db) for a in assignments],
    )


@router.post("/{qr_id_or_db_id}/assign", response_model=AssignmentResponse)
async def assign_qr(
    qr_id_or_db_id: str,
    request: AssignRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Assign a destination to an unassigned QR code."""
    settings = get_settings()
    if current_user.role == UserRole.OPERATOR and not settings.OPERATOR_CAN_ASSIGN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator assignment is disabled by system administrator.",
        )
    
    qr = _resolve_qr(qr_id_or_db_id, db)
    
    if qr.status == QRStatus.RETIRED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign a retired QR code. Retirement is permanent.",
        )
    if qr.status != QRStatus.UNASSIGNED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"QR code is currently {qr.status.value}. Use reassign endpoint for active codes.",
        )
    
    # Create assignment
    assignment = QRAssignment(
        qr_code_id=qr.id,
        business_name=request.business_name,
        destination_url=request.destination_url,
        notes=request.notes,
        assigned_by=current_user.id,
        is_active=True,
        expiry_date=request.expiry_date,
    )
    db.add(assignment)
    
    # Update QR code
    qr.status = QRStatus.ACTIVE
    qr.current_destination = request.destination_url
    qr.current_business_name = request.business_name
    
    # Audit
    audit = AuditLog(
        user_id=current_user.id,
        action="assign",
        entity_type="qr_code",
        entity_id=qr.id,
        details=json.dumps({
            "qr_id": qr.qr_id,
            "business_name": request.business_name,
            "destination_url": request.destination_url,
        }),
    )
    db.add(audit)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict: This QR code has already been assigned or is locked by another request.",
        )
    db.refresh(assignment)
    
    return assignment_to_response(assignment, db)


@router.post("/{qr_id_or_db_id}/reassign", response_model=AssignmentResponse)
async def reassign_qr(
    qr_id_or_db_id: str,
    request: ReassignRequest,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Reassign a QR code to a new destination (admin only). Requires explicit confirmation."""
    if not request.confirm_reassignment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must set confirm_reassignment to true",
        )
    
    qr = _resolve_qr(qr_id_or_db_id, db)
    
    if qr.status == QRStatus.RETIRED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reassign a retired QR code. Retirement is permanent.",
        )
    if qr.status == QRStatus.UNASSIGNED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reassign an unassigned QR code. Use the assign endpoint.",
        )
    
    # Deactivate current assignment
    current_assignment = db.query(QRAssignment).filter(
        QRAssignment.qr_code_id == qr.id,
        QRAssignment.is_active == True,
    ).first()
    
    if current_assignment:
        current_assignment.is_active = False
        current_assignment.deactivated_at = datetime.utcnow()
        current_assignment.deactivated_by = current_user.id
    
    # Create new assignment
    new_assignment = QRAssignment(
        qr_code_id=qr.id,
        business_name=request.business_name,
        destination_url=request.destination_url,
        notes=request.notes,
        assigned_by=current_user.id,
        is_active=True,
        expiry_date=request.expiry_date,
    )
    db.add(new_assignment)
    
    # Update QR code
    qr.status = QRStatus.ACTIVE
    qr.current_destination = request.destination_url
    qr.current_business_name = request.business_name
    
    # Audit
    old_dest = current_assignment.destination_url if current_assignment else None
    old_biz = current_assignment.business_name if current_assignment else None
    audit = AuditLog(
        user_id=current_user.id,
        action="reassign",
        entity_type="qr_code",
        entity_id=qr.id,
        details=json.dumps({
            "qr_id": qr.qr_id,
            "old_business": old_biz,
            "old_destination": old_dest,
            "new_business": request.business_name,
            "new_destination": request.destination_url,
        }),
    )
    db.add(audit)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict: Concurrent reassignment detected.",
        )
    db.refresh(new_assignment)
    
    return assignment_to_response(new_assignment, db)


@router.post("/{qr_id_or_db_id}/deactivate")
async def deactivate_qr(
    qr_id_or_db_id: str,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Deactivate / disable a QR code (admin only). Sets status to DISABLED while preserving destination and history."""
    qr = _resolve_qr(qr_id_or_db_id, db)
    
    if qr.status == QRStatus.RETIRED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate a retired QR code. Retirement is permanent.",
        )
    if qr.status == QRStatus.UNASSIGNED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate an unassigned QR code.",
        )
    if qr.status == QRStatus.DISABLED:
        return {"message": f"QR code {qr.qr_id} is already disabled"}
    
    qr.status = QRStatus.DISABLED
    # Preserve current_destination and current_business_name for authorized reactivation
    
    audit = AuditLog(
        user_id=current_user.id,
        action="deactivate",
        entity_type="qr_code",
        entity_id=qr.id,
        status="success",
        details=json.dumps({"qr_id": qr.qr_id, "preserved_destination": qr.current_destination}),
    )
    db.add(audit)
    db.commit()
    
    return {
        "message": f"QR code {qr.qr_id} disabled successfully (destination preserved)",
        "qr_id": qr.qr_id,
        "status": qr.status.value,
        "preserved_destination": qr.current_destination,
    }


@router.post("/{qr_id_or_db_id}/reactivate")
async def reactivate_qr(
    qr_id_or_db_id: str,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Reactivate a DISABLED QR code (admin only). Restores active redirection to preserved destination."""
    qr = _resolve_qr(qr_id_or_db_id, db)
    
    if qr.status == QRStatus.RETIRED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Retired QR codes cannot be reactivated. Retirement is a permanent terminal state.",
        )
    if qr.status != QRStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only disabled QR codes can be reactivated. Current status is {qr.status.value}.",
        )
    
    qr.status = QRStatus.ACTIVE
    
    audit = AuditLog(
        user_id=current_user.id,
        action="reactivate",
        entity_type="qr_code",
        entity_id=qr.id,
        status="success",
        details=json.dumps({"qr_id": qr.qr_id, "destination_url": qr.current_destination}),
    )
    db.add(audit)
    db.commit()
    
    return {
        "message": f"QR code {qr.qr_id} reactivated successfully",
        "qr_id": qr.qr_id,
        "status": qr.status.value,
        "destination_url": qr.current_destination,
    }


@router.post("/{qr_id_or_db_id}/retire")
async def retire_qr(
    qr_id_or_db_id: str,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Permanently retire a QR code (admin only). Terminal state."""
    qr = _resolve_qr(qr_id_or_db_id, db)
    
    if qr.status == QRStatus.RETIRED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="QR code is already retired.",
        )
    
    # Deactivate current assignment if any
    current_assignment = db.query(QRAssignment).filter(
        QRAssignment.qr_code_id == qr.id,
        QRAssignment.is_active == True,
    ).first()
    
    if current_assignment:
        current_assignment.is_active = False
        current_assignment.deactivated_at = datetime.utcnow()
        current_assignment.deactivated_by = current_user.id
    
    qr.status = QRStatus.RETIRED
    qr.current_destination = None
    qr.current_business_name = None
    
    audit = AuditLog(
        user_id=current_user.id,
        action="retire",
        entity_type="qr_code",
        entity_id=qr.id,
        status="success",
        details=json.dumps({"qr_id": qr.qr_id}),
    )
    db.add(audit)
    db.commit()
    
    return {
        "message": f"QR code {qr.qr_id} retired permanently. This action is terminal.",
        "qr_id": qr.qr_id,
        "status": qr.status.value,
    }


@router.post("/{qr_id_or_db_id}/recover")
async def recover_qr(
    qr_id_or_db_id: str,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Reject reactivation of retired QR codes (RETIRED is permanent terminal state)."""
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Retired QR codes cannot be reactivated. Retirement is a permanent terminal state.",
    )


def _resolve_qr(qr_id_or_db_id: str, db: Session) -> QRCode:
    """Resolve a QR code by QR-ID string, token, or database ID."""
    qr = None
    if qr_id_or_db_id.startswith("QR-"):
        qr = db.query(QRCode).filter(QRCode.qr_id == qr_id_or_db_id).first()
    elif len(qr_id_or_db_id) >= 20:
        qr = db.query(QRCode).filter(QRCode.token == qr_id_or_db_id).first()
    else:
        try:
            db_id = int(qr_id_or_db_id)
            qr = db.query(QRCode).filter(QRCode.id == db_id).first()
        except ValueError:
            pass
    
    if not qr:
        # Fallback check by token in case token was short or didn't match above
        qr = db.query(QRCode).filter(QRCode.token == qr_id_or_db_id).first()
    
    if not qr:
        raise HTTPException(status_code=404, detail="QR code not found")
    return qr
