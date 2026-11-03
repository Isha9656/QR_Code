import os
os.environ["TESTING"] = "1"
import json
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.auth import hash_password
from app.models import User, UserRole, QRCode, QRAssignment, QRStatus, QRScanEvent, AuditLog
from app.services.cleanup_service import verify_and_cleanup_test_qrs, CONFIRMED_TEST_QR_IDS

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_phase4_cleanup.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_phase4_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    admin = User(
        username="phase4_admin",
        password_hash=hash_password("AdminSecure#2026"),
        display_name="Phase 4 Admin",
        role=UserRole.ADMIN,
        is_active=True,
        must_change_password=False,
    )
    operator = User(
        username="phase4_operator",
        password_hash=hash_password("OperatorSecure#2026"),
        display_name="Phase 4 Operator",
        role=UserRole.OPERATOR,
        is_active=True,
        must_change_password=False,
    )
    db.add_all([admin, operator])
    db.commit()

    # Seed the 6 Confirmed Test QRs
    test_qrs = [
        QRCode(qr_id="QR-000063", token="6FJSVUM9HS4R", status=QRStatus.ACTIVE, current_destination="https://concurrentbiz0.com", current_business_name="Concurrent Biz 0"),
        QRCode(qr_id="QR-000083", token="DRsq2iLaOtcl", status=QRStatus.ACTIVE, current_destination="https://concurrentbiz0.com", current_business_name="Concurrent Biz 0"),
        QRCode(qr_id="QR-000111", token="xRTgJJVTw01g", status=QRStatus.ACTIVE, current_destination="https://phase2.internal.example.com", current_business_name="Phase 2 Test Enterprise"),
        QRCode(qr_id="QR-000121", token="QwIPP6K4QRQZ", status=QRStatus.ACTIVE, current_destination="https://phase2.internal.example.com", current_business_name="Phase 2 Test Enterprise"),
        QRCode(qr_id="QR-000131", token="XEAOM1p2p8fT", status=QRStatus.ACTIVE, current_destination="https://secondary.internal.example.com", current_business_name="Phase 2 Secondary Logistics"),
        QRCode(qr_id="QR-000141", token="QUgY2tbhuC3F", status=QRStatus.ACTIVE, current_destination="https://secondary.internal.example.com", current_business_name="Phase 2 Secondary Logistics"),
    ]
    db.add_all(test_qrs)
    db.commit()

    for q in test_qrs:
        a = QRAssignment(
            qr_code_id=q.id,
            business_name=q.current_business_name,
            destination_url=q.current_destination,
            assigned_by=admin.id,
            is_active=True,
        )
        db.add(a)

    # Seed PowerFit Gym (Legitimate / Protected Client with Scans)
    pf1 = QRCode(qr_id="QR-000061", token="dkTCwifHg5gM", status=QRStatus.ACTIVE, current_destination="https://powerfitgym.example.com/join", current_business_name="PowerFit Gym")
    pf2 = QRCode(qr_id="QR-000081", token="IrxlVHeId953", status=QRStatus.ACTIVE, current_destination="https://powerfitgym.example.com/join", current_business_name="PowerFit Gym")
    db.add_all([pf1, pf2])
    db.commit()

    db.add_all([
        QRAssignment(qr_code_id=pf1.id, business_name="PowerFit Gym", destination_url="https://powerfitgym.example.com/join", assigned_by=admin.id, is_active=True),
        QRAssignment(qr_code_id=pf2.id, business_name="PowerFit Gym", destination_url="https://powerfitgym.example.com/join", assigned_by=admin.id, is_active=True),
        QRScanEvent(qr_code_id=pf1.id, result_type="redirect", ip_address="127.0.0.1"),
        QRScanEvent(qr_code_id=pf2.id, result_type="redirect", ip_address="127.0.0.1"),
    ])
    db.commit()

    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


def _get_token(username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_cleanup_six_confirmed_test_qrs():
    """Verify Option A test cleanup safely unassigns the 6 QRs, preserves PowerFit Gym, and is idempotent."""
    admin_token = _get_token("phase4_admin", "AdminSecure#2026")
    headers = {"Authorization": f"Bearer {admin_token}"}
    db = TestingSessionLocal()

    # Pre-check: All 6 test QRs are ACTIVE
    for qid in CONFIRMED_TEST_QR_IDS:
        qr = db.query(QRCode).filter(QRCode.qr_id == qid).first()
        assert qr.status == QRStatus.ACTIVE
        assert qr.current_business_name is not None

    # Execute cleanup via API endpoint
    res = client.post("/api/admin/inventory/cleanup-test-data", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["cleaned_count"] == 6
    assert set(data["cleaned_qr_ids"]) == set(CONFIRMED_TEST_QR_IDS)

    # Post-check: All 6 test QRs are UNASSIGNED, business & destination cleared, tokens preserved
    db.expire_all()
    for qid in CONFIRMED_TEST_QR_IDS:
        qr = db.query(QRCode).filter(QRCode.qr_id == qid).first()
        assert qr.status == QRStatus.UNASSIGNED
        assert qr.current_business_name is None
        assert qr.current_destination is None
        assert qr.token is not None  # Permanent token strictly preserved!

        # Check assignment history preserved and inactive
        assigns = db.query(QRAssignment).filter(QRAssignment.qr_code_id == qr.id).all()
        assert len(assigns) >= 1
        for a in assigns:
            assert a.is_active is False
            assert a.deactivated_at is not None

        # Check audit log created
        audit = db.query(AuditLog).filter(AuditLog.entity_id == qr.id, AuditLog.action == "cleanup_test_qr").first()
        assert audit is not None
        assert audit.status == "success"

    # Post-check: PowerFit Gym MUST REMAIN COMPLETELY UNTOUCHED!
    pf1 = db.query(QRCode).filter(QRCode.qr_id == "QR-000061").first()
    pf2 = db.query(QRCode).filter(QRCode.qr_id == "QR-000081").first()
    assert pf1.status == QRStatus.ACTIVE
    assert pf1.current_business_name == "PowerFit Gym"
    assert pf2.status == QRStatus.ACTIVE
    assert pf2.current_business_name == "PowerFit Gym"

    # Test idempotency: Running cleanup a 2nd time should succeed cleanly
    res2 = client.post("/api/admin/inventory/cleanup-test-data", headers=headers)
    assert res2.status_code == 200
    assert res2.json()["already_cleaned"] is True
    assert res2.json()["cleaned_count"] == 0

    db.close()


def test_operator_forbidden_from_cleanup():
    """Verify operators cannot execute cleanup."""
    op_token = _get_token("phase4_operator", "OperatorSecure#2026")
    headers = {"Authorization": f"Bearer {op_token}"}
    res = client.post("/api/admin/inventory/cleanup-test-data", headers=headers)
    assert res.status_code == 403


def test_global_search_api():
    """Verify global search across QR IDs, tokens, client names, and destinations."""
    token = _get_token("phase4_admin", "AdminSecure#2026")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Search by QR ID
    res1 = client.get("/api/search/global?q=QR-000061", headers=headers)
    assert res1.status_code == 200
    d1 = res1.json()
    assert len(d1["qr_codes"]) >= 1
    assert d1["qr_codes"][0]["qr_id"] == "QR-000061"
    assert d1["qr_codes"][0]["current_business_name"] == "PowerFit Gym"

    # 2. Search by Token substring
    res2 = client.get("/api/search/global?q=dkTCwif", headers=headers)
    assert res2.status_code == 200
    d2 = res2.json()
    assert len(d2["qr_codes"]) >= 1
    assert d2["qr_codes"][0]["qr_id"] == "QR-000061"

    # 3. Search by Client Name
    res3 = client.get("/api/search/global?q=PowerFit", headers=headers)
    assert res3.status_code == 200
    d3 = res3.json()
    assert len(d3["clients"]) >= 1
    assert d3["clients"][0]["client_name"] == "PowerFit Gym"
    assert d3["clients"][0]["total_qrs"] == 2
    assert d3["clients"][0]["active_qrs"] == 2

    # 4. Search by Destination URL
    res4 = client.get("/api/search/global?q=powerfitgym.example", headers=headers)
    assert res4.status_code == 200
    d4 = res4.json()
    assert len(d4["qr_codes"]) >= 1

    # 5. Short query (< 2 chars) returns empty gracefully
    res5 = client.get("/api/search/global?q=a", headers=headers)
    assert res5.status_code == 200
    assert res5.json()["total_matches"] == 0

    # 6. Operator can also use search
    op_token = _get_token("phase4_operator", "OperatorSecure#2026")
    res_op = client.get("/api/search/global?q=PowerFit", headers={"Authorization": f"Bearer {op_token}"})
    assert res_op.status_code == 200
    assert len(res_op.json()["clients"]) >= 1
