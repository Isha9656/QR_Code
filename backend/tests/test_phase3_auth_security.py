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


def test_query_param_token_authentication_fallback():
    """Verify that endpoints requiring authentication support token passed via ?token= query parameter."""
    login_resp = client.post("/api/auth/login", json={"username": "normal_admin", "password": "AdminSecure#2026"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # Request without header but with query parameter ?token=
    resp_with_param = client.get(f"/api/auth/me?token={token}")
    assert resp_with_param.status_code == 200
    assert resp_with_param.json()["username"] == "normal_admin"

    # Invalid query param token must return 401
    resp_invalid_param = client.get("/api/auth/me?token=invalid.jwt.token")
    assert resp_invalid_param.status_code == 401


def test_cors_origins_settings_parsing():
    """Verify Settings parses comma-separated CORS_ORIGINS from environment variables."""
    from app.config import Settings
    import os

    old_env = os.environ.get("CORS_ORIGINS")
    try:
        os.environ["CORS_ORIGINS"] = "http://localhost:5173, https://app.example.com, http://127.0.0.1:3000"
        s = Settings()
        assert "http://localhost:5173" in s.CORS_ORIGINS
        assert "https://app.example.com" in s.CORS_ORIGINS
        assert "http://127.0.0.1:3000" in s.CORS_ORIGINS
        assert len(s.CORS_ORIGINS) == 3
    finally:
        if old_env is not None:
            os.environ["CORS_ORIGINS"] = old_env
        else:
            os.environ.pop("CORS_ORIGINS", None)


def test_jwt_subject_resolution_and_security():
    """Verify numeric ID, string username, inactive rejection, and non-resolving token security."""
    db = TestingSessionLocal()
    
    # Create an inactive user for testing
    inactive_user = User(
        username="disabled_user",
        password_hash=hash_password("Pass123!Safe"),
        display_name="Disabled User",
        role=UserRole.OPERATOR,
        is_active=False,
        must_change_password=False,
    )
    db.add(inactive_user)
    db.commit()
    inactive_id = inactive_user.id
    
    normal_admin = db.query(User).filter(User.username == "normal_admin").first()
    admin_id = normal_admin.id
    db.close()

    # 1. Numeric user ID subject
    numeric_token = create_access_token(data={"sub": str(admin_id), "role": "admin"})
    resp_numeric = client.get("/api/auth/me", headers={"Authorization": f"Bearer {numeric_token}"})
    assert resp_numeric.status_code == 200
    assert resp_numeric.json()["username"] == "normal_admin"

    # 2. Legacy string username subject
    legacy_token = create_access_token(data={"sub": "normal_admin", "role": "admin"})
    resp_legacy = client.get("/api/auth/me", headers={"Authorization": f"Bearer {legacy_token}"})
    assert resp_legacy.status_code == 200
    assert resp_legacy.json()["username"] == "normal_admin"

    # 3. Inactive user with numeric subject must be rejected (401)
    inactive_num_token = create_access_token(data={"sub": str(inactive_id), "role": "operator"})
    resp_inactive_num = client.get("/api/auth/me", headers={"Authorization": f"Bearer {inactive_num_token}"})
    assert resp_inactive_num.status_code == 401
    assert "not found or inactive" in resp_inactive_num.json()["detail"].lower()

    # 4. Inactive user with username subject must be rejected (401)
    inactive_str_token = create_access_token(data={"sub": "disabled_user", "role": "operator"})
    resp_inactive_str = client.get("/api/auth/me", headers={"Authorization": f"Bearer {inactive_str_token}"})
    assert resp_inactive_str.status_code == 401
    assert "not found or inactive" in resp_inactive_str.json()["detail"].lower()

    # 5. Non-existent user subject
    fake_token = create_access_token(data={"sub": "non_existent_ghost_999", "role": "admin"})
    resp_fake = client.get("/api/auth/me", headers={"Authorization": f"Bearer {fake_token}"})
    assert resp_fake.status_code == 401

    # 6. Non-existent numeric ID
    fake_id_token = create_access_token(data={"sub": "999999", "role": "admin"})
    resp_fake_id = client.get("/api/auth/me", headers={"Authorization": f"Bearer {fake_id_token}"})
    assert resp_fake_id.status_code == 401
