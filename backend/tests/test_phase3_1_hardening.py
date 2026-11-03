import os
os.environ["TESTING"] = "1"
import json
import sqlite3
import shutil
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.auth import hash_password
from app.models import User, UserRole, QRCode, QRAssignment, QRStatus, AuditLog
from app.config import get_settings
from app.core.limiter import limiter
from app.schemas import AssignRequest, ReassignRequest
from app.services.backup_service import create_online_backup, validate_sqlite_backup
from restore_database import restore_database

settings = get_settings()
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_phase3_1_hardening.db"
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
def setup_hardening_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    admin = User(
        username="sec_admin",
        password_hash=hash_password("AdminPass123!"),
        display_name="Security Admin",
        role=UserRole.ADMIN,
        is_active=True,
        must_change_password=False,
    )
    operator = User(
        username="sec_operator",
        password_hash=hash_password("OperatorPass123!"),
        display_name="Security Operator",
        role=UserRole.OPERATOR,
        is_active=True,
        must_change_password=False,
    )
    db.add_all([admin, operator])
    db.commit()
    db.close()
    
    yield
    
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()
    if os.path.exists("./test_phase3_1_hardening.db"):
        try:
            os.remove("./test_phase3_1_hardening.db")
        except OSError:
            pass


def get_token(username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return resp.json()["access_token"]


# ============================================================================
# 1. RATE LIMITING ENFORCEMENT (5/minute)
# ============================================================================

def test_login_rate_limiting_enforcement():
    """Verify RATE_LIMIT_AUTH (5/minute) is enforced on /api/auth/login and returns HTTP 429."""
    limiter.enabled = True
    try:
        # Reset limiter storage for clean state
        limiter.reset()
        
        # First 5 login requests should proceed to authentication check
        for i in range(5):
            resp = client.post(
                "/api/auth/login",
                json={"username": "sec_admin", "password": "WrongPassword999!"},
                headers={"X-Forwarded-For": "198.51.100.1"}  # Fixed client IP
            )
            # Should fail auth with 401, not rate limited
            assert resp.status_code == 401, f"Attempt {i+1} failed with {resp.status_code}"
        
        # 6th request from same IP must exceed 5/minute limit -> 429
        rate_limited_resp = client.post(
            "/api/auth/login",
            json={"username": "sec_admin", "password": "WrongPassword999!"},
            headers={"X-Forwarded-For": "198.51.100.1"}
        )
        assert rate_limited_resp.status_code == 429
        assert "rate limit exceeded" in rate_limited_resp.text.lower()
    finally:
        limiter.enabled = False


# ============================================================================
# 2. OPERATOR PERMISSIONS & RBAC
# ============================================================================

def test_operator_permissions_can_assign_toggle():
    """Verify OPERATOR_CAN_ASSIGN setting is strictly enforced by backend assign endpoint."""
    admin_token = get_token("sec_admin", "AdminPass123!")
    op_token = get_token("sec_operator", "OperatorPass123!")
    
    # 1. Admin generates an unassigned QR
    gen_resp = client.post(
        "/api/qr/bulk-generate",
        json={"quantity": 1},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert gen_resp.status_code == 200
    qr_id = gen_resp.json()[0]["qr_id"]
    
    # Case A: When OPERATOR_CAN_ASSIGN is True (default)
    get_settings().OPERATOR_CAN_ASSIGN = True
    assign_resp = client.post(
        f"/api/qr/{qr_id}/assign",
        json={"business_name": "Test Cafe", "destination_url": "https://testcafe.com"},
        headers={"Authorization": f"Bearer {op_token}"}
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["business_name"] == "Test Cafe"
    
    # Generate another QR for disabled test
    gen_resp2 = client.post(
        "/api/qr/bulk-generate",
        json={"quantity": 1},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    qr_id_2 = gen_resp2.json()[0]["qr_id"]
    
    # Case B: When OPERATOR_CAN_ASSIGN is False
    get_settings().OPERATOR_CAN_ASSIGN = False
    try:
        blocked_resp = client.post(
            f"/api/qr/{qr_id_2}/assign",
            json={"business_name": "Blocked Cafe", "destination_url": "https://blockedcafe.com"},
            headers={"Authorization": f"Bearer {op_token}"}
        )
        assert blocked_resp.status_code == 403
        assert "Operator assignment is disabled" in blocked_resp.json()["detail"]
        
        # Verify admin can STILL assign even when OPERATOR_CAN_ASSIGN is False
        admin_assign = client.post(
            f"/api/qr/{qr_id_2}/assign",
            json={"business_name": "Admin Assigned Cafe", "destination_url": "https://admincafe.com"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert admin_assign.status_code == 200
    finally:
        # Restore default
        get_settings().OPERATOR_CAN_ASSIGN = True


def test_operator_forbidden_from_admin_endpoints():
    """Verify operators cannot invoke admin-only endpoints."""
    op_token = get_token("sec_operator", "OperatorPass123!")
    headers = {"Authorization": f"Bearer {op_token}"}
    
    # Bulk generate
    assert client.post("/api/qr/bulk-generate", json={"quantity": 5}, headers=headers).status_code == 403
    # Reassign
    assert client.post("/api/qr/QR-00000001/reassign", json={"business_name": "X", "destination_url": "https://x.com", "confirm_reassignment": True}, headers=headers).status_code == 403
    # Deactivate
    assert client.post("/api/qr/QR-00000001/deactivate", headers=headers).status_code == 403
    # Reactivate
    assert client.post("/api/qr/QR-00000001/reactivate", headers=headers).status_code == 403
    # Retire
    assert client.post("/api/qr/QR-00000001/retire", headers=headers).status_code == 403
    # Recover
    assert client.post("/api/qr/QR-00000001/recover", headers=headers).status_code == 403
    # Backup
    assert client.post("/api/admin/backups", headers=headers).status_code == 403
    assert client.get("/api/admin/backups", headers=headers).status_code == 403
    # Audit logs
    assert client.get("/api/admin/audit-logs", headers=headers).status_code == 403
    # Create user
    assert client.post("/api/auth/users", json={"username": "bad", "password": "BadPassword123!", "display_name": "Bad", "role": "operator"}, headers=headers).status_code == 403


# ============================================================================
# 3. QR LIFECYCLE SECURITY & RETIREMENT TERMINAL STATE
# ============================================================================

def test_qr_lifecycle_full_security():
    """
    Test complete lifecycle transitions:
    - Disabled QR preserves destination & business name.
    - Disabled QR can be reactivated.
    - Retired QR is strictly terminal: reject assign, reassign, reactivate, and recover.
    - Permanent token is preserved across all states.
    - Audit history is preserved.
    """
    admin_token = get_token("sec_admin", "AdminPass123!")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 1. Create QR
    gen = client.post("/api/qr/bulk-generate", json={"quantity": 1}, headers=headers)
    qr_id = gen.json()[0]["qr_id"]
    
    # Read initial QR details to capture permanent token
    detail_0 = client.get(f"/api/qr/{qr_id}", headers=headers).json()
    permanent_token = detail_0["token"]
    assert len(permanent_token) >= 12
    assert detail_0["status"] == "unassigned"
    
    # 2. Assign QR
    assign_resp = client.post(
        f"/api/qr/{qr_id}/assign",
        json={"business_name": "Alpha Corp", "destination_url": "https://alphacorp.example.com"},
        headers=headers
    )
    assert assign_resp.status_code == 200
    
    # Verify token unchanged
    detail_1 = client.get(f"/api/qr/{qr_id}", headers=headers).json()
    assert detail_1["token"] == permanent_token
    assert detail_1["status"] == "active"
    
    # 3. Deactivate QR (disabled state)
    deact_resp = client.post(f"/api/qr/{qr_id}/deactivate", headers=headers)
    assert deact_resp.status_code == 200
    assert deact_resp.json()["status"] == "disabled"
    
    # Verify destination is preserved while disabled
    detail_2 = client.get(f"/api/qr/{qr_id}", headers=headers).json()
    assert detail_2["token"] == permanent_token
    assert detail_2["status"] == "disabled"
    assert detail_2["current_destination"] == "https://alphacorp.example.com"
    assert detail_2["current_business_name"] == "Alpha Corp"
    
    # 4. Reactivate QR
    react_resp = client.post(f"/api/qr/{qr_id}/reactivate", headers=headers)
    assert react_resp.status_code == 200
    assert react_resp.json()["status"] == "active"
    
    detail_3 = client.get(f"/api/qr/{qr_id}", headers=headers).json()
    assert detail_3["token"] == permanent_token
    assert detail_3["status"] == "active"
    assert detail_3["current_destination"] == "https://alphacorp.example.com"
    
    # 5. Permanently Retire QR
    retire_resp = client.post(f"/api/qr/{qr_id}/retire", headers=headers)
    assert retire_resp.status_code == 200
    assert retire_resp.json()["status"] == "retired"
    
    detail_4 = client.get(f"/api/qr/{qr_id}", headers=headers).json()
    assert detail_4["token"] == permanent_token  # Permanent token STILL preserved
    assert detail_4["status"] == "retired"
    
    # 6. Verify RETIRED QR is rejected across all 4 operations:
    
    # 6a. Assignment rejection
    rej_assign = client.post(
        f"/api/qr/{qr_id}/assign",
        json={"business_name": "Try Assign", "destination_url": "https://tryassign.com"},
        headers=headers
    )
    assert rej_assign.status_code == 400
    assert "cannot assign a retired qr code" in rej_assign.json()["detail"].lower()
    
    # 6b. Reassignment rejection
    rej_reassign = client.post(
        f"/api/qr/{qr_id}/reassign",
        json={"business_name": "Try Reassign", "destination_url": "https://tryreassign.com", "confirm_reassignment": True},
        headers=headers
    )
    assert rej_reassign.status_code == 400
    assert "cannot reassign a retired qr code" in rej_reassign.json()["detail"].lower()
    
    # 6c. Reactivation rejection
    rej_reactivate = client.post(f"/api/qr/{qr_id}/reactivate", headers=headers)
    assert rej_reactivate.status_code == 400
    assert "retired qr codes cannot be reactivated" in rej_reactivate.json()["detail"].lower()
    
    # 6d. Recovery rejection
    rej_recover = client.post(f"/api/qr/{qr_id}/recover", headers=headers)
    assert rej_recover.status_code == 400
    assert "retired qr codes cannot be reactivated" in rej_recover.json()["detail"].lower()
    
    # 7. Audit and assignment history preservation
    hist = client.get(f"/api/qr/{qr_id}/history", headers=headers)
    assert hist.status_code == 200
    hist_data = hist.json()
    assert hist_data["qr_id"] == qr_id
    assert len(hist_data["assignments"]) >= 1
    assert hist_data["assignments"][0]["business_name"] == "Alpha Corp"


# ============================================================================
# 4. AUDIT LOG INTEGRITY & FILTERING
# ============================================================================

def test_audit_log_immutability_and_filtering():
    """Verify audit log immutability, failed security recording, absence of passwords/JWTs, and filters."""
    admin_token = get_token("sec_admin", "AdminPass123!")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 1. Immutability - HTTP methods PUT, POST, DELETE are not allowed on audit logs
    assert client.delete("/api/admin/audit-logs", headers=headers).status_code in (404, 405)
    assert client.put("/api/admin/audit-logs", headers=headers).status_code in (404, 405)
    assert client.post("/api/admin/audit-logs", json={}, headers=headers).status_code in (404, 405)
    
    # 2. Trigger a failed security action (invalid current password)
    failed_change = client.post(
        "/api/auth/change-password",
        json={"current_password": "WrongPassword!", "new_password": "ValidNewPass#123"},
        headers=headers
    )
    assert failed_change.status_code == 400
    
    # 3. Query audit logs and verify failed security action is recorded
    audit_resp = client.get("/api/admin/audit-logs?action=password_change_failed", headers=headers)
    assert audit_resp.status_code == 200
    items = audit_resp.json()["items"]
    assert len(items) >= 1
    failed_item = items[0]
    assert failed_item["status"] == "failed"
    assert failed_item["action"] == "password_change_failed"
    
    # 4. Verify audit details NEVER expose passwords or JWT tokens
    all_logs = client.get("/api/admin/audit-logs?per_page=100", headers=headers).json()["items"]
    for log in all_logs:
        details_str = str(log.get("details") or "").lower()
        assert "adminpass123!" not in details_str
        assert "wrongpassword!" not in details_str
        assert "operatorpass123!" not in details_str
        assert "eyjhbgcioi" not in details_str  # Common JWT prefix header
        assert "access_token" not in details_str
    
    # 5. Verify Pagination and all supported filter parameters
    # Filter by action
    login_logs = client.get("/api/admin/audit-logs?action=login", headers=headers).json()
    assert all(l["action"] == "login" for l in login_logs["items"])
    
    # Filter by status
    failed_logs = client.get("/api/admin/audit-logs?status=failed", headers=headers).json()
    assert all(l["status"] == "failed" for l in failed_logs["items"])
    
    # Filter by entity_type
    qr_logs = client.get("/api/admin/audit-logs?entity_type=qr_code", headers=headers).json()
    assert all(l["entity_type"] == "qr_code" for l in qr_logs["items"])
    
    # Pagination
    p1 = client.get("/api/admin/audit-logs?page=1&per_page=2", headers=headers).json()
    p2 = client.get("/api/admin/audit-logs?page=2&per_page=2", headers=headers).json()
    assert p1["page"] == 1
    assert p2["page"] == 2
    if p1["total"] > 2:
        assert p1["items"][0]["id"] != p2["items"][0]["id"]


# ============================================================================
# 5. URL VALIDATION TEST MATRIX
# ============================================================================

def test_url_validation_matrix():
    """Verify URL validation permits valid public schemes/ports/IPv4/IPv6 and blocks SSRF/metadata/loopback/unsafe schemes."""
    # Valid URLs
    valid_urls = [
        "http://example.com",
        "https://example.com",
        "https://sub.domain.company.co.uk",
        "https://api.business.com:8443/webhook/v1?token=123",
        "http://93.184.216.34:8080/path",  # Public IPv4 with custom port
        "https://[2001:db8::1]:8443/api",   # Public IPv6 with custom port
    ]
    for url in valid_urls:
        req = AssignRequest(business_name="Valid URL Test", destination_url=url)
        assert req.destination_url == url.strip()
        req2 = ReassignRequest(business_name="Valid URL Test", destination_url=url, confirm_reassignment=True)
        assert req2.destination_url == url.strip()
    
    # Invalid URLs with specific security threats
    invalid_urls = [
        ("javascript:alert(1)", "Only HTTP and HTTPS URLs are allowed"),
        ("data:text/html,Hello", "Only HTTP and HTTPS URLs are allowed"),
        ("ftp://ftp.example.com", "Only HTTP and HTTPS URLs are allowed"),
        ("https://admin:pass@example.com", "URLs with embedded credentials are not allowed"),
        ("http://169.254.169.254/latest/meta-data/", "Link-local / cloud metadata IP address"),
        ("http://127.0.0.1:8000/", "Loopback IP address"),
        ("http://[::1]:8000/", "Loopback IP address"),
        ("http://0.0.0.0:8000/", "Unspecified IP address"),
        ("https://invalid..domain.com/", "improper domain structure"),
        ("https://invalid domain.com/", "URL cannot contain whitespace"),
    ]
    for bad_url, expected_err in invalid_urls:
        with pytest.raises(ValueError) as excinfo:
            AssignRequest(business_name="Bad URL Test", destination_url=bad_url)
        assert expected_err.lower() in str(excinfo.value).lower(), f"URL '{bad_url}' did not raise expected '{expected_err}', got '{excinfo.value}'"


# ============================================================================
# 6. BACKUP & RECOVERY SAFETY GUARANTEES
# ============================================================================

def test_backup_and_recovery_safety_guarantees(tmp_path):
    """
    Test live backup under active operations, SQLite integrity,
    safe restoration on a separate database, safety backup creation,
    and failure atomicity (corrupt backup does not overwrite target).
    """
    test_db = str(tmp_path / "active_qr_test.db")
    backup_folder = str(tmp_path / "backups")
    os.makedirs(backup_folder, exist_ok=True)
    
    # 1. Initialize source test DB with realistic QR and assignment data
    src_conn = sqlite3.connect(test_db)
    src_cur = src_conn.cursor()
    src_cur.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT);")
    src_cur.execute("CREATE TABLE qr_codes (id INTEGER PRIMARY KEY, qr_id TEXT, token TEXT, status TEXT);")
    src_cur.execute("CREATE TABLE qr_assignments (id INTEGER PRIMARY KEY, qr_code_id INTEGER, destination_url TEXT);")
    src_cur.execute("INSERT INTO users VALUES (1, 'admin');")
    src_cur.execute("INSERT INTO qr_codes VALUES (1, 'QR-TEST01', 'token12345678', 'active');")
    src_cur.execute("INSERT INTO qr_assignments VALUES (1, 1, 'https://original.com');")
    src_conn.commit()
    
    # 2. Perform online backup while connection is active
    backup_result = create_online_backup(test_db, backup_dir=backup_folder)
    assert backup_result["integrity"] == "ok"
    backup_filepath = backup_result["filepath"]
    assert os.path.exists(backup_filepath)
    
    # 3. Verify SQLite integrity
    validation = validate_sqlite_backup(backup_filepath)
    assert validation["valid"] is True
    assert validation["integrity"] == "ok"
    src_conn.close()
    
    # 4. Test safe restoration on a separate target database
    target_restore_db = str(tmp_path / "restored_qr_system.db")
    # Place existing data in target to confirm pre-restore safety snapshot creation
    t_conn = sqlite3.connect(target_restore_db)
    t_conn.execute("CREATE TABLE dummy (x TEXT);")
    t_conn.execute("INSERT INTO dummy VALUES ('old_data');")
    t_conn.commit()
    t_conn.close()
    
    # Run restore
    restore_database(backup_file=backup_filepath, target_db=target_restore_db)
    
    # Confirm safety snapshot was created
    safety_backups = list(tmp_path.glob("restored_qr_system.db.pre_restore_*.bak"))
    assert len(safety_backups) == 1, "Safety snapshot was not created before restoration!"
    
    # Confirm data was restored accurately
    r_conn = sqlite3.connect(target_restore_db)
    r_cur = r_conn.cursor()
    r_cur.execute("SELECT qr_id, token, status FROM qr_codes WHERE id=1;")
    row = r_cur.fetchone()
    assert row == ('QR-TEST01', 'token12345678', 'active')
    
    r_cur.execute("SELECT destination_url FROM qr_assignments WHERE id=1;")
    assert r_cur.fetchone()[0] == 'https://original.com'
    r_conn.close()
    
    # 5. Confirm corrupt backup does NOT replace target database
    corrupt_backup = str(tmp_path / "corrupt.db")
    with open(corrupt_backup, "wb") as f:
        f.write(b"NOT_A_SQLITE_DATABASE_GARBAGE_CONTENT_HERE")
    
    with pytest.raises(SystemExit):
        restore_database(backup_file=corrupt_backup, target_db=target_restore_db)
    
    # Verify target database still contains the valid restored data, not corrupt garbage
    check_conn = sqlite3.connect(target_restore_db)
    check_cur = check_conn.cursor()
    check_cur.execute("SELECT count(*) FROM qr_codes;")
    assert check_cur.fetchone()[0] == 1
    check_conn.close()
