import os
os.environ["TESTING"] = "1"
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.auth import hash_password
from app.models import User, UserRole, AuditLog

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_phase3_audit.db"
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
def setup_audit_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    admin = User(
        username="audit_admin",
        password_hash=hash_password("AuditAdmin#2026"),
        display_name="Audit Admin",
        role=UserRole.ADMIN,
        is_active=True,
        must_change_password=False,
    )
    operator = User(
        username="audit_op",
        password_hash=hash_password("AuditOp#2026"),
        display_name="Audit Operator",
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


def test_audit_trail_recording_and_filtering():
    # 1. Login as admin
    login_resp = client.post("/api/auth/login", json={"username": "audit_admin", "password": "AuditAdmin#2026"})
    admin_token = login_resp.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Trigger failed login to generate a failure audit record
    client.post("/api/auth/login", json={"username": "audit_admin", "password": "wrong_password"})

    # 3. Create a QR code and assign it
    gen = client.post("/api/qr/bulk-generate", headers=admin_headers, json={"quantity": 1})
    qr = gen.json()[0]
    client.post(f"/api/qr/{qr['qr_id']}/assign", headers=admin_headers, json={
        "business_name": "Audit Test Corp",
        "destination_url": "https://audited.example.com"
    })

    # 4. Fetch audit logs (admin only)
    logs_resp = client.get("/api/admin/audit-logs", headers=admin_headers)
    assert logs_resp.status_code == 200
    data = logs_resp.json()
    assert data["total"] > 0
    items = data["items"]

    # Verify no passwords or tokens in any audit details
    for item in items:
        det = str(item.get("details", ""))
        assert "password" not in det.lower() or "attempted_username" in det
        assert "wrong_password" not in det
        assert "admin#2026" not in det.lower()
        assert "bearer" not in det.lower()

    # 5. Filter by action='assign'
    assign_logs = client.get("/api/admin/audit-logs?action=assign", headers=admin_headers)
    assert assign_logs.status_code == 200
    for it in assign_logs.json()["items"]:
        assert it["action"] == "assign"

    # 6. Filter by status='failed'
    failed_logs = client.get("/api/admin/audit-logs?status=failed", headers=admin_headers)
    assert failed_logs.status_code == 200
    for it in failed_logs.json()["items"]:
        assert it["status"] == "failed"

    # 7. Operator access forbidden
    op_login = client.post("/api/auth/login", json={"username": "audit_op", "password": "AuditOp#2026"})
    op_token = op_login.json()["access_token"]
    op_resp = client.get("/api/admin/audit-logs", headers={"Authorization": f"Bearer {op_token}"})
    assert op_resp.status_code == 403
