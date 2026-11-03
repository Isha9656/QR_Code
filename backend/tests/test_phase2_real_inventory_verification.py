import os
os.environ["TESTING"] = "1"
import json
import time
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.auth import hash_password
from app.models import User, UserRole, QRCode, QRAssignment, QRStatus, QRScanEvent, AuditLog
from app.services.client_service import (
    get_distinct_client_names,
    get_clients_overview_summary,
    get_clients_list,
    get_client_details,
    activate_client_qr,
    deactivate_client_qr,
    bulk_activate_client_qrs,
    bulk_deactivate_client_qrs,
    deactivate_all_for_client,
    activate_all_for_client,
    get_client_analytics,
)

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_phase2_verification.db"
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
def setup_phase2_verification_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Users
    admin = User(
        username="verif_admin",
        password_hash=hash_password("AdminSecure#2026"),
        display_name="Verification Admin",
        role=UserRole.ADMIN,
        is_active=True,
        must_change_password=False,
    )
    operator = User(
        username="verif_operator",
        password_hash=hash_password("OperatorSecure#2026"),
        display_name="Verification Operator",
        role=UserRole.OPERATOR,
        is_active=True,
        must_change_password=False,
    )
    db.add_all([admin, operator])
    db.commit()

    # Seed Inventory:
    # Client 1: Alpha Corp (3 QRs: 1 Active, 1 Disabled, 1 Retired)
    q1 = QRCode(qr_id="QR-ALP01", token="tokalpha001111", status=QRStatus.ACTIVE, current_destination="https://alpha.example.com/one", current_business_name="Alpha Corp")
    q2 = QRCode(qr_id="QR-ALP02", token="tokalpha002222", status=QRStatus.DISABLED, current_destination="https://alpha.example.com/two", current_business_name="Alpha Corp")
    q3 = QRCode(qr_id="QR-ALP03", token="tokalpha003333", status=QRStatus.RETIRED, current_destination=None, current_business_name="Alpha Corp")

    # Client 2: Beta Logistics (2 QRs: 2 Active) - one with trailing space in business name to test normalization
    q4 = QRCode(qr_id="QR-BET01", token="tokbeta001111", status=QRStatus.ACTIVE, current_destination="https://beta.example.com/ship", current_business_name="Beta Logistics")
    q5 = QRCode(qr_id="QR-BET02", token="tokbeta002222", status=QRStatus.ACTIVE, current_destination="https://beta.example.com/track", current_business_name="Beta Logistics ")

    # Unassigned QRs (2 QRs: unassigned warehouse stock, must never be in client inventory)
    q6 = QRCode(qr_id="QR-UNAS01", token="tokunas001111", status=QRStatus.UNASSIGNED, current_destination=None, current_business_name=None)
    q7 = QRCode(qr_id="QR-UNAS02", token="tokunas002222", status=QRStatus.UNASSIGNED, current_destination=None, current_business_name=None)

    db.add_all([q1, q2, q3, q4, q5, q6, q7])
    db.commit()

    # Assignments
    a1 = QRAssignment(qr_code_id=q1.id, business_name="Alpha Corp", destination_url="https://alpha.example.com/one", assigned_by=admin.id, is_active=True)
    a2 = QRAssignment(qr_code_id=q2.id, business_name="Alpha Corp", destination_url="https://alpha.example.com/two", assigned_by=admin.id, is_active=False)
    a3 = QRAssignment(qr_code_id=q3.id, business_name="Alpha Corp", destination_url="https://alpha.example.com/old", assigned_by=admin.id, is_active=False)
    a4 = QRAssignment(qr_code_id=q4.id, business_name="Beta Logistics", destination_url="https://beta.example.com/ship", assigned_by=admin.id, is_active=True)
    a5 = QRAssignment(qr_code_id=q5.id, business_name="Beta Logistics ", destination_url="https://beta.example.com/track", assigned_by=admin.id, is_active=True)

    db.add_all([a1, a2, a3, a4, a5])
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


def _get_token(username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_client_inventory_counts_and_unassigned_exclusion():
    """Verify client counts against database, verify unassigned QRs are excluded, verify deduplication."""
    db = TestingSessionLocal()
    
    # Check distinct clients
    names = get_distinct_client_names(db)
    # Beta Logistics and 'Beta Logistics ' must be deduplicated into 1 client
    assert "Alpha Corp" in names
    assert "Beta Logistics" in names
    assert len(names) == 2, f"Expected 2 deduplicated clients, got {names}"

    summary = get_clients_overview_summary(db)
    assert summary["total_clients"] == 2
    assert summary["total_qr_codes"] == 5  # 3 Alpha + 2 Beta. (Excludes 2 unassigned!)
    assert summary["active_qr_codes"] == 3  # 1 Alpha + 2 Beta
    assert summary["disabled_qr_codes"] == 1  # 1 Alpha
    assert summary["retired_qr_codes"] == 1  # 1 Alpha

    # Client list
    res = get_clients_list(db, page=1, per_page=10)
    assert res["total"] == 2
    assert len(res["items"]) == 2

    alpha = next(c for c in res["items"] if c["client_name"] == "Alpha Corp")
    assert alpha["total_qr_codes"] == 3
    assert alpha["active_qr_codes"] == 1
    assert alpha["disabled_qr_codes"] == 1
    assert alpha["retired_qr_codes"] == 1

    beta = next(c for c in res["items"] if c["client_name"] == "Beta Logistics")
    assert beta["total_qr_codes"] == 2
    assert beta["active_qr_codes"] == 2
    assert beta["disabled_qr_codes"] == 0
    assert beta["retired_qr_codes"] == 0

    db.close()


def test_public_scan_tracking_vs_camera_preview_and_latency():
    """Verify public redirect tracking, camera preview separation, invalid token exclusion, and redirect speed."""
    db = TestingSessionLocal()
    q1 = db.query(QRCode).filter(QRCode.qr_id == "QR-ALP01").first()
    token = q1.token
    
    initial_scans = db.query(QRScanEvent).filter(QRScanEvent.qr_code_id == q1.id).count()

    # 1. Camera preview via /api/qr/resolve/{token}
    preview_res = client.get(f"/api/qr/resolve/{token}")
    assert preview_res.status_code == 200
    data = preview_res.json()
    assert data["qr_id"] == "QR-ALP01"
    assert data["status"].upper() == "ACTIVE"

    # Verify scan count did NOT increment on internal preview
    db.expire_all()
    preview_scans = db.query(QRScanEvent).filter(QRScanEvent.qr_code_id == q1.id).count()
    assert preview_scans == initial_scans, "Camera preview must not increment scan events"

    # 2. Public redirect via /q/{token}
    start_time = time.perf_counter()
    redirect_res = client.get(f"/q/{token}", follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 TestBrowser", "X-Forwarded-For": "198.51.100.45"})
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    
    assert redirect_res.status_code in [302, 307]
    assert redirect_res.headers["location"] == "https://alpha.example.com/one"
    assert elapsed_ms < 50, f"Redirect took too long: {elapsed_ms:.2f}ms"

    # Verify scan event recorded
    db.expire_all()
    after_scans = db.query(QRScanEvent).filter(QRScanEvent.qr_code_id == q1.id).count()
    assert after_scans == initial_scans + 1

    # Check IP anonymization on recorded scan event
    event = db.query(QRScanEvent).filter(QRScanEvent.qr_code_id == q1.id).order_by(QRScanEvent.id.desc()).first()
    assert event.result_type == "redirect"
    assert event.ip_address == "198.51.100.0", f"IP was not properly anonymized: {event.ip_address}"

    # 3. Invalid token
    invalid_res = client.get("/q/invalid_nonexistent_token_9999", follow_redirects=False)
    assert invalid_res.status_code == 404
    invalid_scans = db.query(QRScanEvent).filter(QRScanEvent.qr_code_id == q1.id).count()
    assert invalid_scans == after_scans

    db.close()


def test_individual_and_bulk_lifecycle_management():
    """Test individual and bulk activation/deactivation, client-level operations, token/destination preservation."""
    admin_token = _get_token("verif_admin", "AdminSecure#2026")
    headers = {"Authorization": f"Bearer {admin_token}"}
    db = TestingSessionLocal()

    # 1. Individual activate QR-ALP02 (currently DISABLED)
    q2 = db.query(QRCode).filter(QRCode.qr_id == "QR-ALP02").first()
    assert q2.status == QRStatus.DISABLED
    dest_before = q2.current_destination
    token_before = q2.token

    act_res = client.post(f"/api/clients/Alpha Corp/qr/{q2.qr_id}/activate", headers=headers)
    assert act_res.status_code == 200, act_res.text
    db.expire_all()
    q2_updated = db.query(QRCode).filter(QRCode.qr_id == "QR-ALP02").first()
    assert q2_updated.status == QRStatus.ACTIVE
    assert q2_updated.current_destination == dest_before, "Destination must be preserved"
    assert q2_updated.token == token_before, "Token must never change"

    # Verify audit log
    audit = db.query(AuditLog).filter(AuditLog.entity_id == q2.id, AuditLog.action == "client_qr_activate").order_by(AuditLog.id.desc()).first()
    assert audit is not None
    assert audit.status == "success"

    # 2. Individual deactivate QR-ALP02
    deact_res = client.post(f"/api/clients/Alpha Corp/qr/{q2.qr_id}/deactivate", headers=headers)
    assert deact_res.status_code == 200, deact_res.text
    db.expire_all()
    q2_updated = db.query(QRCode).filter(QRCode.qr_id == "QR-ALP02").first()
    assert q2_updated.status == QRStatus.DISABLED
    assert q2_updated.current_destination == dest_before

    # 3. Bulk activate QR-ALP02
    bulk_act_res = client.post("/api/clients/Alpha Corp/bulk-activate", json={"confirmation": True, "qr_ids": [q2.qr_id]}, headers=headers)
    assert bulk_act_res.status_code == 200, bulk_act_res.text
    assert bulk_act_res.json()["affected_count"] == 1
    db.expire_all()
    assert db.query(QRCode).filter(QRCode.qr_id == "QR-ALP02").first().status == QRStatus.ACTIVE

    # 4. Client-level deactivate-all for Alpha Corp
    deact_all_res = client.post("/api/clients/Alpha Corp/deactivate-all", headers=headers)
    assert deact_all_res.status_code == 200, deact_all_res.text
    db.expire_all()
    # QR-ALP01 and QR-ALP02 should now both be DISABLED
    assert db.query(QRCode).filter(QRCode.qr_id == "QR-ALP01").first().status == QRStatus.DISABLED
    assert db.query(QRCode).filter(QRCode.qr_id == "QR-ALP02").first().status == QRStatus.DISABLED
    # QR-ALP03 was RETIRED and must remain RETIRED
    assert db.query(QRCode).filter(QRCode.qr_id == "QR-ALP03").first().status == QRStatus.RETIRED
    # Beta Logistics should remain ACTIVE and unaffected!
    assert db.query(QRCode).filter(QRCode.qr_id == "QR-BET01").first().status == QRStatus.ACTIVE

    # 5. Client-level reactivate-all for Alpha Corp
    react_all_res = client.post("/api/clients/Alpha Corp/activate-all", headers=headers)
    assert react_all_res.status_code == 200, react_all_res.text
    db.expire_all()
    assert db.query(QRCode).filter(QRCode.qr_id == "QR-ALP01").first().status == QRStatus.ACTIVE
    assert db.query(QRCode).filter(QRCode.qr_id == "QR-ALP02").first().status == QRStatus.ACTIVE
    # RETIRED must still remain RETIRED
    assert db.query(QRCode).filter(QRCode.qr_id == "QR-ALP03").first().status == QRStatus.RETIRED

    db.close()


def test_retired_qr_protection_against_activation():
    """Verify retired QRs cannot be activated individually, in bulk, or via activate-all."""
    admin_token = _get_token("verif_admin", "AdminSecure#2026")
    headers = {"Authorization": f"Bearer {admin_token}"}
    db = TestingSessionLocal()
    q3 = db.query(QRCode).filter(QRCode.qr_id == "QR-ALP03").first()
    assert q3.status == QRStatus.RETIRED

    # Single activation attempt on retired QR
    single_res = client.post(f"/api/clients/Alpha Corp/qr/{q3.qr_id}/activate", headers=headers)
    assert single_res.status_code == 400
    assert "retired" in single_res.json()["detail"].lower()

    # Bulk activation attempt including retired QR
    bulk_res = client.post("/api/clients/Alpha Corp/bulk-activate", json={"confirmation": True, "qr_ids": [q3.qr_id]}, headers=headers)
    assert bulk_res.status_code == 200
    assert bulk_res.json()["affected_count"] == 0
    assert bulk_res.json()["skipped_count"] == 1

    db.expire_all()
    assert db.query(QRCode).filter(QRCode.qr_id == "QR-ALP03").first().status == QRStatus.RETIRED
    db.close()


def test_operator_rbac_restrictions():
    """Verify operators can view client details and analytics, but get 403 on all mutating operations."""
    op_token = _get_token("verif_operator", "OperatorSecure#2026")
    headers = {"Authorization": f"Bearer {op_token}"}
    db = TestingSessionLocal()
    q1 = db.query(QRCode).filter(QRCode.qr_id == "QR-ALP01").first()

    # Operator CAN read
    assert client.get("/api/clients", headers=headers).status_code == 200
    assert client.get("/api/clients/Alpha Corp", headers=headers).status_code == 200
    assert client.get("/api/clients/Alpha Corp/analytics", headers=headers).status_code == 200

    # Operator CANNOT mutate (403 Forbidden)
    assert client.post(f"/api/clients/Alpha Corp/qr/{q1.qr_id}/deactivate", headers=headers).status_code == 403
    assert client.post("/api/clients/Alpha Corp/bulk-deactivate", json={"confirmation": True, "qr_ids": [q1.qr_id]}, headers=headers).status_code == 403
    assert client.post("/api/clients/Alpha Corp/deactivate-all", headers=headers).status_code == 403
    assert client.post("/api/clients/Alpha Corp/activate-all", headers=headers).status_code == 403

    db.close()


def test_index_usage_and_performance():
    """Verify sqlite query planner utilizes indexes on current_business_name and qr_scan_events."""
    db = TestingSessionLocal()
    
    # 1. Verify index on QRCode.current_business_name
    plan1 = db.execute(text("EXPLAIN QUERY PLAN SELECT id FROM qr_codes WHERE current_business_name = 'Alpha Corp'")).fetchall()
    plan1_str = " ".join(str(p) for p in plan1)
    assert "ix_qr_codes_current_business_name" in plan1_str or "USING INDEX" in plan1_str, f"Index not used: {plan1_str}"

    # 2. Verify index on QRScanEvent
    plan2 = db.execute(text("EXPLAIN QUERY PLAN SELECT id FROM qr_scan_events WHERE qr_code_id = 1 AND result_type = 'redirect'")).fetchall()
    plan2_str = " ".join(str(p) for p in plan2)
    assert "ix_scan_events_qr_result_scanned" in plan2_str or "USING INDEX" in plan2_str, f"Index not used: {plan2_str}"

    db.close()
