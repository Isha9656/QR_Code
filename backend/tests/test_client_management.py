import os
os.environ["TESTING"] = "1"
import json
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.auth import hash_password
from app.models import User, UserRole, QRCode, QRAssignment, QRStatus, QRScanEvent, AuditLog
from app.services.client_service import (
    get_clients_overview_summary, get_clients_list, get_client_details,
    activate_client_qr, deactivate_client_qr, bulk_activate_client_qrs,
    bulk_deactivate_client_qrs, deactivate_all_for_client, activate_all_for_client,
    get_client_analytics
)

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_client_management.db"
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
def setup_client_management_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # 1. Users: Admin and Operator
    admin = User(
        username="client_admin",
        password_hash=hash_password("AdminSecure#2026"),
        display_name="Client Admin",
        role=UserRole.ADMIN,
        is_active=True,
        must_change_password=False,
    )
    operator = User(
        username="client_operator",
        password_hash=hash_password("OperatorSecure#2026"),
        display_name="Client Operator",
        role=UserRole.OPERATOR,
        is_active=True,
        must_change_password=False,
    )
    db.add_all([admin, operator])
    db.commit()
    
    # 2. QR Codes for Client A ("Acme Corp")
    # QR 1: Active, 10 scans
    qr1 = QRCode(qr_id="QR-ACME01", token="tokenacme001111222", status=QRStatus.ACTIVE, current_destination="https://acme.com/menu", current_business_name="Acme Corp")
    # QR 2: Active, 0 scans (never scanned)
    qr2 = QRCode(qr_id="QR-ACME02", token="tokenacme002222333", status=QRStatus.ACTIVE, current_destination="https://acme.com/promo", current_business_name="Acme Corp")
    # QR 3: Disabled, 5 scans (old scans > 30 days ago)
    qr3 = QRCode(qr_id="QR-ACME03", token="tokenacme003333444", status=QRStatus.DISABLED, current_destination="https://acme.com/old", current_business_name="Acme Corp")
    # QR 4: Retired, 2 scans
    qr4 = QRCode(qr_id="QR-ACME04", token="tokenacme004444555", status=QRStatus.RETIRED, current_destination=None, current_business_name="Acme Corp")
    
    # 3. QR Codes for Client B ("Beta LLC")
    # QR 5: Active, 20 scans
    qr5 = QRCode(qr_id="QR-BETA01", token="tokenbeta005555666", status=QRStatus.ACTIVE, current_destination="https://beta.com/store", current_business_name="Beta LLC")
    # QR 6: Disabled
    qr6 = QRCode(qr_id="QR-BETA02", token="tokenbeta006666777", status=QRStatus.DISABLED, current_destination="https://beta.com/support", current_business_name="Beta LLC")
    
    # 4. QR Code Unassigned (no client)
    qr7 = QRCode(qr_id="QR-UNASS1", token="tokenunassigned999", status=QRStatus.UNASSIGNED)
    
    db.add_all([qr1, qr2, qr3, qr4, qr5, qr6, qr7])
    db.commit()
    
    # 5. Assignments
    now = datetime.utcnow()
    a1 = QRAssignment(qr_code_id=qr1.id, business_name="Acme Corp", destination_url="https://acme.com/menu", is_active=True, assigned_by=admin.id, assigned_at=now - timedelta(days=60))
    a2 = QRAssignment(qr_code_id=qr2.id, business_name="Acme Corp", destination_url="https://acme.com/promo", is_active=True, assigned_by=admin.id, assigned_at=now - timedelta(days=40))
    a3 = QRAssignment(qr_code_id=qr3.id, business_name="Acme Corp", destination_url="https://acme.com/old", is_active=True, assigned_by=admin.id, assigned_at=now - timedelta(days=50))
    a4 = QRAssignment(qr_code_id=qr4.id, business_name="Acme Corp", destination_url="https://acme.com/retired", is_active=False, assigned_by=admin.id, assigned_at=now - timedelta(days=90))
    a5 = QRAssignment(qr_code_id=qr5.id, business_name="Beta LLC", destination_url="https://beta.com/store", is_active=True, assigned_by=admin.id, assigned_at=now - timedelta(days=20))
    a6 = QRAssignment(qr_code_id=qr6.id, business_name="Beta LLC", destination_url="https://beta.com/support", is_active=True, assigned_by=admin.id, assigned_at=now - timedelta(days=15))
    db.add_all([a1, a2, a3, a4, a5, a6])
    db.commit()
    
    # 6. Scan Events
    # QR 1: 10 redirect scans (8 recent, 2 older)
    for i in range(8):
        db.add(QRScanEvent(qr_code_id=qr1.id, scanned_at=now - timedelta(days=i), result_type="redirect", ip_address="192.168.1.0"))
    for i in range(2):
        db.add(QRScanEvent(qr_code_id=qr1.id, scanned_at=now - timedelta(days=40 + i), result_type="redirect", ip_address="192.168.1.0"))
    
    # QR 3: 5 scans all older than 35 days
    for i in range(5):
        db.add(QRScanEvent(qr_code_id=qr3.id, scanned_at=now - timedelta(days=35 + i), result_type="redirect", ip_address="192.168.1.0"))
    # Also 2 disabled scan attempts (should not count as redirect)
    db.add(QRScanEvent(qr_code_id=qr3.id, scanned_at=now - timedelta(days=1), result_type="disabled", ip_address="192.168.1.0"))
    
    # QR 4: 2 retired scans (old)
    for i in range(2):
        db.add(QRScanEvent(qr_code_id=qr4.id, scanned_at=now - timedelta(days=80 + i), result_type="redirect", ip_address="192.168.1.0"))
    
    # QR 5: 20 scans within last 14 days
    for i in range(20):
        db.add(QRScanEvent(qr_code_id=qr5.id, scanned_at=now - timedelta(days=i % 10), result_type="redirect", ip_address="192.168.2.0"))
    
    db.commit()
    db.close()
    
    yield
    
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()
    if os.path.exists("./test_client_management.db"):
        try:
            os.remove("./test_client_management.db")
        except OSError:
            pass


def get_token(username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return resp.json()["access_token"]


# ============================================================================
# 1. CLIENT OVERVIEW & DASHBOARD SUMMARY
# ============================================================================

def test_client_overview_summary_cards():
    """Verify high-level summary cards return accurate database counts."""
    admin_token = get_token("client_admin", "AdminSecure#2026")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    resp = client.get("/api/clients/overview", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["total_clients"] == 2  # Acme Corp, Beta LLC
    assert data["total_qr_codes"] == 6  # Excludes unassigned QR-UNASS1
    assert data["active_qr_codes"] == 3  # QR1, QR2, QR5
    assert data["disabled_qr_codes"] == 2  # QR3, QR6
    assert data["retired_qr_codes"] == 1  # QR4
    assert data["qr_codes_without_recent_usage"] >= 2  # QR2 (never scanned), QR3 (old scan > 30d), QR6 (never scanned)


def test_client_list_pagination_and_sorting():
    """Test client list endpoint with search, sorting, and pagination."""
    admin_token = get_token("client_admin", "AdminSecure#2026")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 1. List all clients
    resp = client.get("/api/clients", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert "summary" in data
    
    # 2. Search for Acme
    search_resp = client.get("/api/clients?search=acme", headers=headers)
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["total"] == 1
    acme = search_data["items"][0]
    assert acme["client_name"] == "Acme Corp"
    assert acme["total_qr_codes"] == 4
    assert acme["active_qr_codes"] == 2
    assert acme["disabled_qr_codes"] == 1
    assert acme["retired_qr_codes"] == 1
    assert acme["total_scans"] == 17  # QR1 (10) + QR3 (5) + QR4 (2)
    assert acme["never_scanned_count"] == 1  # QR2
    assert acme["not_scanned_30d_count"] == 2  # QR2 (never) + QR3 (>30d)
    
    # 3. Sort by total_scans descending (Beta has 20 scans, Acme has 17)
    sort_resp = client.get("/api/clients?sort_by=total_scans&sort_dir=desc", headers=headers)
    assert sort_resp.status_code == 200
    items = sort_resp.json()["items"]
    assert items[0]["client_name"] == "Beta LLC"
    assert items[0]["total_scans"] == 20
    assert items[1]["client_name"] == "Acme Corp"


# ============================================================================
# 2. INDIVIDUAL CLIENT DETAILS & FILTERS
# ============================================================================

def test_individual_client_details_and_filters():
    """Verify detailed client QR list with status filters and search."""
    admin_token = get_token("client_admin", "AdminSecure#2026")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # All QRs for Acme Corp
    resp = client.get("/api/clients/Acme Corp", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["client_name"] == "Acme Corp"
    assert data["total_qr_codes"] == 4
    assert len(data["items"]) == 4
    
    # Filter by active
    active_resp = client.get("/api/clients/Acme Corp?status_filter=active", headers=headers)
    assert active_resp.status_code == 200
    active_items = active_resp.json()["items"]
    assert len(active_items) == 2
    assert all(i["status"] == "active" for i in active_items)
    
    # Filter by disabled
    disabled_resp = client.get("/api/clients/Acme Corp?status_filter=disabled", headers=headers)
    assert disabled_resp.status_code == 200
    disabled_items = disabled_resp.json()["items"]
    assert len(disabled_items) == 1
    assert disabled_items[0]["qr_id"] == "QR-ACME03"
    assert disabled_items[0]["status"] == "disabled"
    assert disabled_items[0]["destination_url"] == "https://acme.com/old"
    
    # Filter by never_scanned
    never_resp = client.get("/api/clients/Acme Corp?status_filter=never_scanned", headers=headers)
    assert never_resp.status_code == 200
    never_items = never_resp.json()["items"]
    assert len(never_items) == 1
    assert never_items[0]["qr_id"] == "QR-ACME02"
    assert never_items[0]["total_scans"] == 0
    
    # Filter by not_used_30d
    not_30d_resp = client.get("/api/clients/Acme Corp?status_filter=not_used_30d", headers=headers)
    assert not_30d_resp.status_code == 200
    not_30d_items = not_30d_resp.json()["items"]
    assert len(not_30d_items) == 2  # QR2 (never) and QR3 (>30d)
    
    # Search by destination
    search_dest = client.get("/api/clients/Acme Corp?search=promo", headers=headers)
    assert search_dest.status_code == 200
    assert len(search_dest.json()["items"]) == 1
    assert search_dest.json()["items"][0]["qr_id"] == "QR-ACME02"


# ============================================================================
# 3. QR USAGE TRACKING & PRIVACY-SAFE ANONYMIZATION
# ============================================================================

def test_qr_usage_tracking_public_redirect():
    """Verify public redirect increments successful scan count, ignores preview scanner, and anonymizes IP."""
    # Read QR1 total scans before
    db = TestingSessionLocal()
    before_scans = db.query(QRScanEvent).filter(QRScanEvent.qr_code_id == 1, QRScanEvent.result_type == "redirect").count()
    db.close()
    
    # Public redirect via /q/{token}
    redir_resp = client.get("/q/tokenacme001111222", follow_redirects=False, headers={"User-Agent": "TestBrowser/1.0", "X-Forwarded-For": "203.0.113.195"})
    assert redir_resp.status_code == 302
    assert redir_resp.headers["location"] == "https://acme.com/menu"
    
    # Verify scan event added and anonymized
    db = TestingSessionLocal()
    after_scans = db.query(QRScanEvent).filter(QRScanEvent.qr_code_id == 1, QRScanEvent.result_type == "redirect").count()
    assert after_scans == before_scans + 1
    
    latest_event = db.query(QRScanEvent).filter(QRScanEvent.qr_code_id == 1).order_by(QRScanEvent.scanned_at.desc()).first()
    assert latest_event.result_type == "redirect"
    assert latest_event.ip_address is not None
    # Verify host octet is masked
    assert latest_event.ip_address.endswith(".0") or "anonymized" in latest_event.ip_address
    
    # Admin preview resolver via /api/qr/resolve/{token} does NOT record a public redirect scan
    before_preview = db.query(QRScanEvent).filter(QRScanEvent.qr_code_id == 1, QRScanEvent.result_type == "redirect").count()
    resolve_resp = client.get("/api/qr/resolve/tokenacme001111222")
    assert resolve_resp.status_code == 200
    after_preview = db.query(QRScanEvent).filter(QRScanEvent.qr_code_id == 1, QRScanEvent.result_type == "redirect").count()
    assert after_preview == before_preview, "Preview scan should not increment public redirect scan event!"
    db.close()


# ============================================================================
# 4. ACTIVATION & DEACTIVATION MANAGEMENT (INDIVIDUAL & BULK)
# ============================================================================

def test_individual_activation_and_deactivation():
    """Verify single activation/deactivation with audit logs and destination preservation."""
    admin_token = get_token("client_admin", "AdminSecure#2026")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 1. Activate disabled QR-ACME03
    act_resp = client.post("/api/clients/Acme Corp/qr/QR-ACME03/activate", headers=headers)
    assert act_resp.status_code == 200
    act_data = act_resp.json()
    assert act_data["status"] == "active"
    assert act_data["destination_url"] == "https://acme.com/old"
    
    # 2. Deactivate active QR-ACME03 (preserves destination)
    deact_resp = client.post("/api/clients/Acme Corp/qr/QR-ACME03/deactivate", headers=headers)
    assert deact_resp.status_code == 200
    deact_data = deact_resp.json()
    assert deact_data["status"] == "disabled"
    assert deact_data["preserved_destination"] == "https://acme.com/old"
    
    # 3. Cross-client protection: try activating Beta's QR under Acme's path
    cross_resp = client.post("/api/clients/Acme Corp/qr/QR-BETA02/activate", headers=headers)
    assert cross_resp.status_code == 400
    assert "does not belong to client" in cross_resp.json()["detail"].lower()


def test_bulk_activation_and_deactivation():
    """Verify bulk activation/deactivation endpoints with confirmation requirement and audit logs."""
    admin_token = get_token("client_admin", "AdminSecure#2026")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 1. Attempt bulk deactivate without confirmation -> 400
    no_confirm = client.post("/api/clients/Acme Corp/bulk-deactivate", json={
        "qr_ids": ["QR-ACME01", "QR-ACME02"],
        "confirmation": False,
    }, headers=headers)
    assert no_confirm.status_code == 400
    assert "confirmation to true" in no_confirm.json()["detail"].lower()
    
    # 2. Bulk deactivate QR-ACME01 and QR-ACME02 with confirmation -> 200
    bulk_deact = client.post("/api/clients/Acme Corp/bulk-deactivate", json={
        "qr_ids": ["QR-ACME01", "QR-ACME02"],
        "confirmation": True,
    }, headers=headers)
    assert bulk_deact.status_code == 200
    data = bulk_deact.json()
    assert data["affected_count"] == 2
    assert "QR-ACME01" in data["affected_qr_ids"]
    assert "QR-ACME02" in data["affected_qr_ids"]
    
    # 3. Bulk reactivate QR-ACME01 and QR-ACME02
    bulk_act = client.post("/api/clients/Acme Corp/bulk-activate", json={
        "qr_ids": ["QR-ACME01", "QR-ACME02"],
        "confirmation": True,
    }, headers=headers)
    assert bulk_act.status_code == 200
    act_data = bulk_act.json()
    assert act_data["affected_count"] == 2


def test_client_level_deactivate_and_activate_all():
    """Verify client-wide deactivation and reactivation operations."""
    admin_token = get_token("client_admin", "AdminSecure#2026")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 1. Deactivate ALL active QRs for Beta LLC (QR-BETA01 is active)
    deact_all = client.post("/api/clients/Beta LLC/deactivate-all", headers=headers)
    assert deact_all.status_code == 200
    assert deact_all.json()["affected_count"] >= 1
    
    # Verify Beta LLC has 0 active QRs
    b_detail = client.get("/api/clients/Beta LLC", headers=headers).json()
    assert b_detail["active_qr_codes"] == 0
    assert b_detail["disabled_qr_codes"] == 2  # Both QR-BETA01 and QR-BETA02 now disabled
    
    # 2. Reactivate ALL disabled QRs for Beta LLC
    act_all = client.post("/api/clients/Beta LLC/activate-all", headers=headers)
    assert act_all.status_code == 200
    assert act_all.json()["affected_count"] == 2
    
    # Verify Beta LLC has 2 active QRs
    b_detail_after = client.get("/api/clients/Beta LLC", headers=headers).json()
    assert b_detail_after["active_qr_codes"] == 2
    assert b_detail_after["disabled_qr_codes"] == 0


def test_retired_qr_protection():
    """Verify retired QR codes are strictly rejected from activation and bulk modification."""
    admin_token = get_token("client_admin", "AdminSecure#2026")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 1. Single activate attempt on retired QR-ACME04
    rej_act = client.post("/api/clients/Acme Corp/qr/QR-ACME04/activate", headers=headers)
    assert rej_act.status_code == 400
    assert "retired qr codes cannot be activated" in rej_act.json()["detail"].lower()
    
    # 2. Single deactivate attempt on retired QR-ACME04
    rej_deact = client.post("/api/clients/Acme Corp/qr/QR-ACME04/deactivate", headers=headers)
    assert rej_deact.status_code == 400
    assert "cannot deactivate a retired qr code" in rej_deact.json()["detail"].lower()
    
    # 3. Bulk activate including retired QR-ACME04 (should skip retired code)
    bulk_skip = client.post("/api/clients/Acme Corp/bulk-activate", json={
        "qr_ids": ["QR-ACME04"],
        "confirmation": True,
    }, headers=headers)
    assert bulk_skip.status_code == 200
    assert bulk_skip.json()["affected_count"] == 0
    assert bulk_skip.json()["skipped_count"] == 1


# ============================================================================
# 5. ROLES & SECURITY ENFORCEMENT
# ============================================================================

def test_operator_rbac_enforcement():
    """Verify operators can view client data but are rejected with HTTP 403 on all mutating operations."""
    op_token = get_token("client_operator", "OperatorSecure#2026")
    headers = {"Authorization": f"Bearer {op_token}"}
    
    # Operator CAN read overview, client list, and client details
    assert client.get("/api/clients/overview", headers=headers).status_code == 200
    assert client.get("/api/clients", headers=headers).status_code == 200
    assert client.get("/api/clients/Acme Corp", headers=headers).status_code == 200
    assert client.get("/api/clients/Acme Corp/analytics", headers=headers).status_code == 200
    
    # Operator CANNOT activate
    assert client.post("/api/clients/Acme Corp/qr/QR-ACME03/activate", headers=headers).status_code == 403
    # Operator CANNOT deactivate
    assert client.post("/api/clients/Acme Corp/qr/QR-ACME01/deactivate", headers=headers).status_code == 403
    # Operator CANNOT bulk activate
    assert client.post("/api/clients/Acme Corp/bulk-activate", json={"qr_ids": ["QR-ACME01"], "confirmation": True}, headers=headers).status_code == 403
    # Operator CANNOT bulk deactivate
    assert client.post("/api/clients/Acme Corp/bulk-deactivate", json={"qr_ids": ["QR-ACME01"], "confirmation": True}, headers=headers).status_code == 403
    # Operator CANNOT deactivate-all
    assert client.post("/api/clients/Acme Corp/deactivate-all", headers=headers).status_code == 403
    # Operator CANNOT activate-all
    assert client.post("/api/clients/Acme Corp/activate-all", headers=headers).status_code == 403


# ============================================================================
# 6. CLIENT USAGE ANALYTICS
# ============================================================================

def test_client_usage_analytics():
    """Verify client usage analytics returns daily, weekly, monthly trends, top/least QRs, and declining usage."""
    admin_token = get_token("client_admin", "AdminSecure#2026")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    resp = client.get("/api/clients/Beta LLC/analytics?days=30", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["client_name"] == "Beta LLC"
    assert data["date_range_days"] == 30
    assert len(data["daily_scans"]) == 30
    assert "weekly_scans" in data
    assert "monthly_scans" in data
    assert len(data["most_used_qrs"]) >= 1
    assert data["most_used_qrs"][0]["qr_id"] == "QR-BETA01"
    assert data["most_used_qrs"][0]["total_scans"] == 20
    assert len(data["no_scan_qrs"]) >= 1
    assert any(q["qr_id"] == "QR-BETA02" for q in data["no_scan_qrs"])
