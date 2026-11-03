import json
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models import QRCode, QRAssignment, QRScanEvent, QRStatus, AuditLog, User

CONFIRMED_TEST_QR_IDS = [
    "QR-000063",
    "QR-000083",
    "QR-000111",
    "QR-000121",
    "QR-000131",
    "QR-000141",
]

PROTECTED_CLIENT_NAMES = ["powerfit gym"]
PROTECTED_QR_IDS = ["QR-000061", "QR-000081"]


def verify_and_cleanup_test_qrs(db: Session, admin_user: User) -> Dict[str, Any]:
    """
    Safely and transactionally cleans up the six confirmed test QR codes (Option A):
    - Deactivates current active assignment
    - Reverts status to UNASSIGNED
    - Clears current_business_name and current_destination
    - Preserves permanent QR tokens and historical assignment records
    - Records immutable audit log entries
    - Protects PowerFit Gym and all legitimate inventory
    - Safe against duplicate / repeated execution (idempotent)
    """
    # 1. Precondition verification: Check protected QRs are safe
    for prot_id in PROTECTED_QR_IDS:
        prot_qr = db.query(QRCode).filter(QRCode.qr_id == prot_id).first()
        if prot_qr and prot_qr.current_business_name:
            assert prot_qr.current_business_name.lower() in PROTECTED_CLIENT_NAMES, (
                f"Integrity check failed: Protected QR {prot_id} has unexpected business {prot_qr.current_business_name}"
            )

    # 2. Check target QRs
    targets = []
    already_cleaned_count = 0

    for qr_id in CONFIRMED_TEST_QR_IDS:
        qr = db.query(QRCode).filter(QRCode.qr_id == qr_id).first()
        if not qr:
            raise ValueError(f"Precondition failed: Confirmed test QR {qr_id} does not exist in database.")

        # Check if already cleaned up
        if qr.status == QRStatus.UNASSIGNED and qr.current_business_name is None:
            already_cleaned_count += 1
            targets.append((qr, None, None, True))
            continue

        # Check that it has ZERO public redirect scans
        redirect_scans = (
            db.query(QRScanEvent)
            .filter(QRScanEvent.qr_code_id == qr.id, QRScanEvent.result_type == "redirect")
            .count()
        )
        if redirect_scans > 0:
            raise ValueError(
                f"Precondition failed: QR {qr_id} has {redirect_scans} public redirect scans. "
                "Refusing automatic cleanup on scanned QR code."
            )

        # Check that it has not been reassigned to a protected business
        if qr.current_business_name and qr.current_business_name.lower() in PROTECTED_CLIENT_NAMES:
            raise ValueError(
                f"Precondition failed: QR {qr_id} is assigned to protected client '{qr.current_business_name}'."
            )

        targets.append((qr, qr.current_business_name, qr.current_destination, False))

    # If all are already cleaned, return idempotent success
    if already_cleaned_count == len(CONFIRMED_TEST_QR_IDS):
        return {
            "success": True,
            "already_cleaned": True,
            "cleaned_count": 0,
            "cleaned_qr_ids": CONFIRMED_TEST_QR_IDS,
            "message": "All 6 confirmed test QR codes are already unassigned and cleaned up.",
        }

    # 3. Transactional cleanup execution
    cleaned_ids = []
    for qr, old_biz, old_dest, was_cleaned in targets:
        if was_cleaned:
            continue

        # Deactivate any active assignments
        active_assignments = (
            db.query(QRAssignment)
            .filter(QRAssignment.qr_code_id == qr.id, QRAssignment.is_active == True)
            .all()
        )
        for assign in active_assignments:
            assign.is_active = False
            assign.deactivated_at = datetime.utcnow()
            assign.deactivated_by = admin_user.id

        # Update QR status to UNASSIGNED and clear business/destination
        qr.status = QRStatus.UNASSIGNED
        qr.current_business_name = None
        qr.current_destination = None
        # Permanent token (qr.token) and identifier (qr.qr_id) remain strictly unchanged

        # Record audit log
        audit = AuditLog(
            user_id=admin_user.id,
            action="cleanup_test_qr",
            entity_type="qr_code",
            entity_id=qr.id,
            status="success",
            details=json.dumps({
                "qr_id": qr.qr_id,
                "token": qr.token,
                "action": "revert_to_unassigned_inventory",
                "cleared_business": old_biz,
                "cleared_destination": old_dest,
                "previous_status": "active",
                "new_status": "unassigned",
            }),
        )
        db.add(audit)
        cleaned_ids.append(qr.qr_id)

    db.commit()

    return {
        "success": True,
        "already_cleaned": False,
        "cleaned_count": len(cleaned_ids),
        "cleaned_qr_ids": cleaned_ids,
        "message": f"Successfully cleaned up {len(cleaned_ids)} test QR codes. Reverted to unassigned inventory.",
    }
