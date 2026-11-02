import os
os.environ["TESTING"] = "1"
import shutil
import sqlite3
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.auth import hash_password
from app.models import User, UserRole
from app.services.backup_service import create_online_backup, validate_sqlite_backup, list_backups
from restore_database import restore_database

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_phase3_backup.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)
TEMP_TEST_BACKUPS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "scratch_backups"))


@pytest.fixture(scope="module", autouse=True)
def setup_backup_db():
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
    
    os.makedirs(TEMP_TEST_BACKUPS_DIR, exist_ok=True)
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()
    if os.path.exists(TEMP_TEST_BACKUPS_DIR):
        shutil.rmtree(TEMP_TEST_BACKUPS_DIR, ignore_errors=True)


def test_online_backup_service_and_validation():
    # 1. Create a dummy sqlite database with sample table
    test_db_path = os.path.join(TEMP_TEST_BACKUPS_DIR, "source_test.db")
    conn = sqlite3.connect(test_db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE assets (id INTEGER PRIMARY KEY, name TEXT);")
    cur.execute("INSERT INTO assets (name) VALUES ('Scanner 101'), ('Printer 202');")
    conn.commit()
    conn.close()

    # 2. Run online backup
    backup_result = create_online_backup(test_db_path, backup_dir=TEMP_TEST_BACKUPS_DIR)
    assert backup_result["integrity"] == "ok"
    assert os.path.exists(backup_result["filepath"])
    assert backup_result["size_bytes"] > 0
    assert len(backup_result["checksum_sha256"]) == 64

    # 3. Validate backup file directly
    validation = validate_sqlite_backup(backup_result["filepath"])
    assert validation["valid"] is True
    assert validation["integrity"] == "ok"

    # 4. Corrupt a test file and verify validator catches it
    corrupt_path = os.path.join(TEMP_TEST_BACKUPS_DIR, "corrupt.db")
    with open(corrupt_path, "wb") as f:
        f.write(b"NOT_A_SQLITE_DATABASE_DATA_GARBAGE_PAYLOAD")
    assert validate_sqlite_backup(corrupt_path)["valid"] is False


def test_offline_database_recovery_tool():
    # 1. Prepare an original test database with data
    original_db = os.path.join(TEMP_TEST_BACKUPS_DIR, "original_app.db")
    conn = sqlite3.connect(original_db)
    cur = conn.cursor()
    cur.execute("CREATE TABLE company_records (id INTEGER PRIMARY KEY, title TEXT);")
    cur.execute("INSERT INTO company_records (title) VALUES ('Crucial Asset Record');")
    conn.commit()
    conn.close()

    # 2. Make a clean validated backup
    backup_meta = create_online_backup(original_db, backup_dir=TEMP_TEST_BACKUPS_DIR)
    backup_file = backup_meta["filepath"]

    # 3. Modify/damage original database
    conn = sqlite3.connect(original_db)
    cur = conn.cursor()
    cur.execute("DELETE FROM company_records;")
    conn.commit()
    conn.close()

    # Verify data is currently gone
    conn = sqlite3.connect(original_db)
    count = conn.execute("SELECT COUNT(*) FROM company_records").fetchone()[0]
    conn.close()
    assert count == 0

    # 4. Perform atomic offline restore using restore_database CLI logic
    restore_database(backup_file, target_db=original_db)

    # 5. Verify restored database has the original data back!
    conn = sqlite3.connect(original_db)
    count_restored = conn.execute("SELECT COUNT(*) FROM company_records").fetchone()[0]
    title_restored = conn.execute("SELECT title FROM company_records LIMIT 1").fetchone()[0]
    conn.close()
    assert count_restored == 1
    assert title_restored == "Crucial Asset Record"


def test_admin_backup_endpoints_and_rbac():
    # Login as admin
    admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Login as operator
    op_login = client.post("/api/auth/login", json={"username": "operator", "password": "operator123"})
    op_token = op_login.json()["access_token"]
    op_headers = {"Authorization": f"Bearer {op_token}"}

    # Operator is forbidden from triggering backup
    op_resp = client.post("/api/admin/backups", headers=op_headers)
    assert op_resp.status_code == 403

    # Operator is forbidden from listing backups
    op_list = client.get("/api/admin/backups", headers=op_headers)
    assert op_list.status_code == 403

    # Admin can list backups
    admin_list = client.get("/api/admin/backups", headers=admin_headers)
    assert admin_list.status_code == 200
    assert "backups" in admin_list.json()
