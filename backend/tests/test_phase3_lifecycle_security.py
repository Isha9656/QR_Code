import os
os.environ["TESTING"] = "1"
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.auth import hash_password
from app.models import User, UserRole, QRCode, QRStatus
from app.config import get_settings

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_phase3_lifecycle.db"
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
def setup_lifecycle_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    admin = User(
        username="admin",
        password_hash=hash_password("admin123"),
        display_name="Admin",
        role=UserRole.ADMIN,
        is_active=True,
        must_change_password=False,
    )
    operator = User(
        username="operator",
        password_hash=hash_password("operator123"),
        display_name="Operator",
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


def test_qr_lifecycle_disabled_and_reactivation():
    # Login
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Generate 1 code
    gen_resp = client.post("/api/qr/bulk-generate", headers=headers, json={"quantity": 1})
    qr = gen_resp.json()[0]
    qr_id = qr["qr_id"]
    qr_token = qr["token"]

    # 1. Initial status: unassigned. Public redirect gives not activated page
    pub1 = client.get(f"/q/{qr_token}")
    assert pub1.status_code == 200
    assert "not been activated yet" in pub1.text

    # 2. Assign
    assign_resp = client.post(f"/api/qr/{qr_id}/assign", headers=headers, json={
        "business_name": "Lifecycle Business A",
        "destination_url": "https://service-a.example.com/portal"
    })
    assert assign_resp.status_code == 200

    # Public redirect redirects to destination
    pub2 = client.get(f"/q/{qr_token}", follow_redirects=False)
    assert pub2.status_code == 302
    assert pub2.headers["location"] == "https://service-a.example.com/portal"

    # 3. Deactivate -> status is DISABLED, destination is preserved
    deact_resp = client.post(f"/api/qr/{qr_id}/deactivate", headers=headers)
    assert deact_resp.status_code == 200
    assert deact_resp.json()["status"] == "disabled"
    assert deact_resp.json()["preserved_destination"] == "https://service-a.example.com/portal"

    # Public redirect for disabled code does NOT redirect
    pub3 = client.get(f"/q/{qr_token}")
    assert pub3.status_code == 200
    assert "temporarily disabled" in pub3.text or "disabled" in pub3.text

    # 4. Reactivate restores active status and destination
    react_resp = client.post(f"/api/qr/{qr_id}/reactivate", headers=headers)
    assert react_resp.status_code == 200
    assert react_resp.json()["status"] == "active"
    assert react_resp.json()["destination_url"] == "https://service-a.example.com/portal"

    # 5. Disable again, then test reassigning while disabled
    client.post(f"/api/qr/{qr_id}/deactivate", headers=headers)
    reassign_resp = client.post(f"/api/qr/{qr_id}/reassign", headers=headers, json={
        "business_name": "Lifecycle Business B",
        "destination_url": "https://service-b.example.com/app",
        "confirm_reassignment": True
    })
    assert reassign_resp.status_code == 200
    assert reassign_resp.json()["is_active"] is True

    # Verify history preserved
    hist_resp = client.get(f"/api/qr/{qr_id}/history", headers=headers)
    assert len(hist_resp.json()["assignments"]) == 2

    # 6. Retire code permanently
    retire_resp = client.post(f"/api/qr/{qr_id}/retire", headers=headers)
    assert retire_resp.status_code == 200
    assert retire_resp.json()["status"] == "retired"

    # Verify retired code cannot be assigned, reassigned, reactivated, or recovered
    r1 = client.post(f"/api/qr/{qr_id}/assign", headers=headers, json={
        "business_name": "Ghost", "destination_url": "https://ghost.com"
    })
    assert r1.status_code == 400
    assert "retired" in r1.json()["detail"].lower()

    r2 = client.post(f"/api/qr/{qr_id}/reassign", headers=headers, json={
        "business_name": "Ghost", "destination_url": "https://ghost.com", "confirm_reassignment": True
    })
    assert r2.status_code == 400
    assert "retired" in r2.json()["detail"].lower()

    r3 = client.post(f"/api/qr/{qr_id}/reactivate", headers=headers)
    assert r3.status_code == 400
    assert "retired" in r3.json()["detail"].lower()

    r4 = client.post(f"/api/qr/{qr_id}/recover", headers=headers)
    assert r4.status_code == 400
    assert "cannot be reactivated" in r4.json()["detail"].lower()


def test_url_validation_rules():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    gen_resp = client.post("/api/qr/bulk-generate", headers=headers, json={"quantity": 1})
    qr_id = gen_resp.json()[0]["qr_id"]

    # Unsafe javascript scheme
    res1 = client.post(f"/api/qr/{qr_id}/assign", headers=headers, json={
        "business_name": "Test", "destination_url": "javascript:alert(1)"
    })
    assert res1.status_code == 422

    # Embedded credentials
    res2 = client.post(f"/api/qr/{qr_id}/assign", headers=headers, json={
        "business_name": "Test", "destination_url": "https://admin:password@malicious.com"
    })
    assert res2.status_code == 422

    # Disallowed cloud metadata IP
    res3 = client.post(f"/api/qr/{qr_id}/assign", headers=headers, json={
        "business_name": "Test", "destination_url": "http://169.254.169.254/latest/meta-data"
    })
    assert res3.status_code == 422

    # Valid complex URL with port and query params
    res4 = client.post(f"/api/qr/{qr_id}/assign", headers=headers, json={
        "business_name": "Valid Enterprise",
        "destination_url": "https://sub.valid-company.com:8443/products/catalog?category=machinery&ref=internal_qr#details"
    })
    assert res4.status_code == 200
    assert res4.json()["is_active"] is True
