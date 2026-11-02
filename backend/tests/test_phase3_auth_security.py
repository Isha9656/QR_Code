import os
os.environ["TESTING"] = "1"
import time
from datetime import datetime, timedelta
import pytest
from jose import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.auth import hash_password, create_access_token
from app.models import User, UserRole, RevokedToken
from app.config import get_settings

settings = get_settings()
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_phase3_auth.db"
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
def setup_auth_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # User requiring password change
    default_admin = User(
        username="default_admin",
        password_hash=hash_password("admin123"),
        display_name="Default Administrator",
        role=UserRole.ADMIN,
        is_active=True,
        must_change_password=True,
    )
    
    # Regular active admin
    normal_admin = User(
        username="normal_admin",
        password_hash=hash_password("AdminSecure#2026"),
        display_name="Normal Administrator",
        role=UserRole.ADMIN,
        is_active=True,
        must_change_password=False,
    )
    
    db.add_all([default_admin, normal_admin])
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


def test_password_enforcement_workflow():
    # 1. Login as default admin
    login_resp = client.post("/api/auth/login", json={"username": "default_admin", "password": "admin123"})
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert data["must_change_password"] is True
    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Blocked from accessing normal operations
    blocked_resp = client.get("/api/qr?status=unassigned", headers=headers)
    assert blocked_resp.status_code == 403
    assert "Password change required" in blocked_resp.json()["detail"]

    # 3. Allowed to access /me
    me_resp = client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["must_change_password"] is True

    # 4. Attempt to change to same default password
    reject_default = client.post("/api/auth/change-password", headers=headers, json={
        "current_password": "admin123",
        "new_password": "admin123"
    })
    assert reject_default.status_code == 422 or reject_default.status_code == 400

    # 5. Attempt to change with weak password
    reject_weak = client.post("/api/auth/change-password", headers=headers, json={
        "current_password": "admin123",
        "new_password": "weakpassword"
    })
    assert reject_weak.status_code == 422  # Fails complexity validation

    # 6. Change to valid strong password
    success_change = client.post("/api/auth/change-password", headers=headers, json={
        "current_password": "admin123",
        "new_password": "BrandNewAdmin$99"
    })
    assert success_change.status_code == 200
    assert success_change.json()["must_change_password"] is False

    # 7. Normal operation now allowed
    allowed_resp = client.get("/api/qr?status=unassigned", headers=headers)
    assert allowed_resp.status_code == 200


def test_persistent_token_revocation_on_logout():
    # 1. Login
    login_resp = client.post("/api/auth/login", json={"username": "normal_admin", "password": "AdminSecure#2026"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Verify token works
    me_resp = client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200

    # 3. Logout
    logout_resp = client.post("/api/auth/logout", headers=headers)
    assert logout_resp.status_code == 200

    # 4. Token must now be rejected
    rejected_resp = client.get("/api/auth/me", headers=headers)
    assert rejected_resp.status_code == 401
    assert "revoked" in rejected_resp.json()["detail"].lower()


def test_invalid_and_expired_jwt():
    # 1. Forged token with invalid signature
    fake_token = jwt.encode({"sub": "1", "role": "admin"}, "wrong_secret_key", algorithm="HS256")
    res1 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {fake_token}"})
    assert res1.status_code == 401

    # 2. Expired token
    expired_payload = {
        "sub": "1",
        "role": "admin",
        "exp": datetime.utcnow() - timedelta(minutes=10)
    }
    expired_token = jwt.encode(expired_payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    res2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res2.status_code == 401
