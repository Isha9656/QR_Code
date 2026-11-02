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

# Use an in-memory or test SQLite database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    # Create test admin
    admin = User(
        username="admin",
        password_hash=hash_password("admin123"),
        display_name="System Administrator",
        role=UserRole.ADMIN,
        is_active=True,
    )
    # Create test operator
    operator = User(
        username="operator",
        password_hash=hash_password("operator123"),
        display_name="Field Operator",
        role=UserRole.OPERATOR,
        is_active=True,
    )
    db.add_all([admin, operator])
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_login_success_and_me():
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    token = data["access_token"]

    # Verify me endpoint
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == "admin"
    assert me_resp.json()["role"] == "admin"


def test_login_invalid_password():
    response = client.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
    assert response.status_code == 401


def test_bulk_generate_qr_codes():
    # Login as admin
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]

    # Bulk generate 5 QR codes
    gen_resp = client.post(
        "/api/qr/bulk-generate",
        json={"quantity": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert gen_resp.status_code == 200
    qr_list = gen_resp.json()
    assert len(qr_list) == 5
    for item in qr_list:
        assert item["status"] == "unassigned"
        assert item["token"] is not None
        assert item["qr_id"].startswith("QR-")


def test_assign_qr_code():
    # Login as operator
    login_resp = client.post("/api/auth/login", json={"username": "operator", "password": "operator123"})
    token = login_resp.json()["access_token"]

    # Get unassigned QR codes
    list_resp = client.get("/api/qr?status=unassigned", headers={"Authorization": f"Bearer {token}"})
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) > 0
    target_qr = items[0]

    # Assign it
    assign_resp = client.post(
        f"/api/qr/{target_qr['qr_id']}/assign",
        json={
            "business_name": "Acme Cafe",
            "destination_url": "https://acmecafe.example.com",
            "notes": "Table 1 sticker",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert assign_resp.status_code == 200
    assigned_data = assign_resp.json()
    assert assigned_data["business_name"] == "Acme Cafe"
    assert assigned_data["destination_url"] == "https://acmecafe.example.com"


def test_public_qr_redirect_and_resolve():
    # Find the assigned QR code
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]

    list_resp = client.get("/api/qr?status=active", headers={"Authorization": f"Bearer {token}"})
    assert list_resp.status_code == 200
    active_qrs = list_resp.json()["items"]
    assert len(active_qrs) > 0
    assigned_qr = active_qrs[0]

    # Test Public Redirect (status 302, should not follow redirect to assert 302)
    redir_resp = client.get(f"/q/{assigned_qr['token']}", follow_redirects=False)
    assert redir_resp.status_code == 302
    assert redir_resp.headers["location"] == "https://acmecafe.example.com"

    # Test Resolver API (for scanner UI)
    resolve_resp = client.get(f"/api/qr/resolve/{assigned_qr['token']}")
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["status"] == "active"
    assert resolve_resp.json()["destination_url"] == "https://acmecafe.example.com"


def test_reassign_qr_code():
    # Login as admin
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]

    list_resp = client.get("/api/qr?status=active", headers={"Authorization": f"Bearer {token}"})
    assigned_qr = list_resp.json()["items"][0]

    # Reassign
    reassign_resp = client.post(
        f"/api/qr/{assigned_qr['qr_id']}/reassign",
        json={
            "business_name": "New Bistro",
            "destination_url": "https://newbistro.example.com",
            "confirm_reassignment": True,
            "notes": "Reassigned for new client",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reassign_resp.status_code == 200
    assert reassign_resp.json()["business_name"] == "New Bistro"

    # Verify history
    hist_resp = client.get(f"/api/qr/{assigned_qr['qr_id']}/history", headers={"Authorization": f"Bearer {token}"})
    assert hist_resp.status_code == 200
    assert len(hist_resp.json()["assignments"]) >= 2


def test_deactivate_and_recover():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]

    list_resp = client.get("/api/qr?status=active", headers={"Authorization": f"Bearer {token}"})
    assigned_qr = list_resp.json()["items"][0]

    # Deactivate (sets DISABLED, preserves destination)
    deact_resp = client.post(f"/api/qr/{assigned_qr['qr_id']}/deactivate", headers={"Authorization": f"Bearer {token}"})
    assert deact_resp.status_code == 200
    assert deact_resp.json()["status"] == "disabled"

    # Reactivate (restores ACTIVE)
    react_resp = client.post(f"/api/qr/{assigned_qr['qr_id']}/reactivate", headers={"Authorization": f"Bearer {token}"})
    assert react_resp.status_code == 200
    assert react_resp.json()["status"] == "active"

    # Retire (terminal state)
    retire_resp = client.post(f"/api/qr/{assigned_qr['qr_id']}/retire", headers={"Authorization": f"Bearer {token}"})
    assert retire_resp.status_code == 200
    assert retire_resp.json()["status"] == "retired"

    # Attempt to recover retired QR must be rejected
    recover_resp = client.post(f"/api/qr/{assigned_qr['qr_id']}/recover", headers={"Authorization": f"Bearer {token}"})
    assert recover_resp.status_code == 400
    assert "cannot be reactivated" in recover_resp.json()["detail"].lower()


def test_analytics_overview():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]

    resp = client.get("/api/analytics/overview", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "total_qr_codes" in data
    assert "active" in data
    assert "unassigned" in data
    assert "total_scans" in data


def test_operator_rbac_restrictions():
    # Login as operator
    login_resp = client.post("/api/auth/login", json={"username": "operator", "password": "operator123"})
    token = login_resp.json()["access_token"]

    # Operator should be forbidden from bulk generation
    gen_resp = client.post(
        "/api/qr/bulk-generate",
        json={"quantity": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert gen_resp.status_code == 403

    # Operator should be forbidden from reassigning
    reassign_resp = client.post(
        "/api/qr/QR-000001/reassign",
        json={
            "business_name": "Test",
            "destination_url": "https://example.com",
            "confirm_reassignment": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reassign_resp.status_code == 403


def test_qr_export_png_and_pdf():
    # Login as admin
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]

    # List codes
    list_resp = client.get("/api/qr", headers={"Authorization": f"Bearer {token}"})
    items = list_resp.json()["items"]
    assert len(items) > 0
    test_id = items[0]["id"]

    # Test PNG export
    png_resp = client.get(f"/api/qr/export/png/{test_id}", headers={"Authorization": f"Bearer {token}"})
    assert png_resp.status_code == 200
    assert png_resp.headers["content-type"] == "image/png"
    assert len(png_resp.content) > 100

    # Test PDF export
    pdf_resp = client.post(
        "/api/qr/export/pdf",
        json={"qr_ids": [test_id], "qr_size_mm": 30, "page_margin_mm": 10, "spacing_mm": 5, "show_labels": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert len(pdf_resp.content) > 100


def test_inventory_stats_and_businesses():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]

    # Test stats
    stats_resp = client.get("/api/qr/stats", headers={"Authorization": f"Bearer {token}"})
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert "total" in stats
    assert "unassigned" in stats
    assert "active" in stats
    assert "disabled" in stats
    assert "retired" in stats

    # Test businesses list
    biz_resp = client.get("/api/qr/businesses", headers={"Authorization": f"Bearer {token}"})
    assert biz_resp.status_code == 200
    assert isinstance(biz_resp.json(), list)


def test_bulk_printing_studio_preview_and_pdf():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]

    # Studio layout preview
    preview_resp = client.post(
        "/api/qr/export/studio-preview",
        json={
            "quantity": 20,
            "qr_size_mm": 30,
            "show_labels": True,
            "company_name": "TEST CORP",
            "header_text": "INTERNAL ASSETS",
            "page_margin_mm": 10,
            "spacing_mm": 5,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert preview_resp.status_code == 200
    preview_data = preview_resp.json()
    assert preview_data["cols"] > 0
    assert preview_data["rows"] > 0
    assert preview_data["total_pages"] >= 1
    assert preview_data["total_qrs"] == 20
    assert len(preview_data["sample_qrs"]) > 0

    # Studio PDF download with quantity
    pdf_resp = client.post(
        "/api/qr/export/studio-pdf",
        json={
            "quantity": 5,
            "qr_size_mm": 30,
            "show_labels": True,
            "company_name": "TEST CORP",
            "header_text": "INTERNAL ASSETS",
            "page_margin_mm": 10,
            "spacing_mm": 5,
            "unassigned_only": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert len(pdf_resp.content) > 1000


def test_bulk_printing_studio_rejects_non_unassigned():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]

    # Bulk generate 2 QRs
    gen_resp = client.post("/api/qr/bulk-generate", json={"quantity": 2}, headers={"Authorization": f"Bearer {token}"})
    qr1 = gen_resp.json()[0]
    qr2 = gen_resp.json()[1]

    # Assign qr1 so it is active
    client.post(
        f"/api/qr/{qr1['qr_id']}/assign",
        json={"business_name": "Studio Test Co", "destination_url": "https://test.example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Attempting to print studio PDF containing active qr1 with unassigned_only=True must fail with 400!
    bad_print = client.post(
        "/api/qr/export/studio-pdf",
        json={
            "qr_ids": [qr1["id"], qr2["id"]],
            "unassigned_only": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bad_print.status_code == 400
    assert "Only unassigned QR codes" in bad_print.json()["detail"]


