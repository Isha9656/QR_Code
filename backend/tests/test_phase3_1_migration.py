import os
os.environ["TESTING"] = "1"
import shutil
import sqlite3
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.auth import create_default_admin, verify_password
from app.models import User, QRCode, QRAssignment, RevokedToken, AuditLog

ORIGINAL_PRE_PHASE3_BAK = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "qr_system.db.pre_phase3_bak"))


def test_existing_database_migration(tmp_path):
    """
    Test Phase 3 migration against an isolated COPY of the actual pre-Phase-3 database.
    CRITICAL: Never runs against the live database.
    
    Verifies:
    1. Existing users remain intact.
    2. Existing QR records remain intact.
    3. Existing permanent tokens remain unchanged.
    4. Assignment history remains intact.
    5. An existing default admin using the default password receives must_change_password = True.
    6. Existing legitimate accounts (e.g., operator or customized password) are NOT locked out.
    7. Revoked token table is created correctly.
    """
    assert os.path.exists(ORIGINAL_PRE_PHASE3_BAK), f"Pre-Phase 3 backup file not found at {ORIGINAL_PRE_PHASE3_BAK}"
    
    # 1. Create isolated copy in temporary path
    test_db_copy = str(tmp_path / "migrated_qr_system_test.db")
    shutil.copy2(ORIGINAL_PRE_PHASE3_BAK, test_db_copy)
    
    # 2. Inspect pre-migration baseline in the copy
    pre_conn = sqlite3.connect(test_db_copy)
    pre_cur = pre_conn.cursor()
    
    pre_users = pre_cur.execute("SELECT id, username, role, password_hash FROM users ORDER BY id").fetchall()
    pre_qr_count = pre_cur.execute("SELECT count(*) FROM qr_codes").fetchone()[0]
    pre_qr_tokens = dict(pre_cur.execute("SELECT id, token FROM qr_codes").fetchall())
    pre_qr_records = pre_cur.execute("SELECT id, qr_id, token, status FROM qr_codes ORDER BY id").fetchall()
    pre_assignments = pre_cur.execute("SELECT id, qr_code_id, business_name, destination_url FROM qr_assignments ORDER BY id").fetchall()
    
    # Check tables before migration
    pre_tables = [r[0] for r in pre_cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    pre_conn.close()
    
    assert len(pre_users) > 0, "Pre-Phase-3 DB had no users"
    assert pre_qr_count > 0, "Pre-Phase-3 DB had no QR codes"
    
    # 3. Perform migration using our schema migration and init logic
    test_engine = create_engine(f"sqlite:///{test_db_copy}", connect_args={"check_same_thread": False})
    
    # Step A: Create any missing tables (e.g., revoked_tokens)
    Base.metadata.create_all(bind=test_engine)
    
    # Step B: Apply column additions (must_change_password, audit status)
    with test_engine.connect() as conn:
        user_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(users)"))]
        if "must_change_password" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0"))
            conn.commit()
        
        audit_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(audit_logs)"))]
        if "status" not in audit_cols:
            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'success'"))
            conn.commit()
    
    # Step C: Run create_default_admin logic to evaluate existing admin passwords
    SessionTest = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = SessionTest()
    try:
        create_default_admin(db)
    finally:
        db.close()
    
    # 4. Verification of migrated database state
    post_conn = sqlite3.connect(test_db_copy)
    post_cur = post_conn.cursor()
    
    # Check 1: Existing users remain intact
    post_users = post_cur.execute("SELECT id, username, role, password_hash FROM users ORDER BY id").fetchall()
    assert len(post_users) == len(pre_users), "User count changed during migration"
    for pre_u, post_u in zip(pre_users, post_users):
        assert pre_u[0] == post_u[0], f"User ID mismatch: {pre_u[0]} != {post_u[0]}"
        assert pre_u[1] == post_u[1], f"Username mismatch: {pre_u[1]} != {post_u[1]}"
        assert pre_u[2] == post_u[2], f"Role mismatch: {pre_u[2]} != {post_u[2]}"
        assert pre_u[3] == post_u[3], f"Password hash altered for user {pre_u[1]}"
    
    # Check 2 & 3: Existing QR records and permanent tokens remain completely unchanged
    post_qr_count = post_cur.execute("SELECT count(*) FROM qr_codes").fetchone()[0]
    assert post_qr_count == pre_qr_count, f"QR count changed from {pre_qr_count} to {post_qr_count}"
    
    post_qr_records = post_cur.execute("SELECT id, qr_id, token, status FROM qr_codes ORDER BY id").fetchall()
    for pre_qr, post_qr in zip(pre_qr_records, post_qr_records):
        assert pre_qr[0] == post_qr[0], f"QR ID altered: {pre_qr[0]} != {post_qr[0]}"
        assert pre_qr[1] == post_qr[1], f"QR code string altered: {pre_qr[1]} != {post_qr[1]}"
        assert pre_qr[2] == post_qr[2], f"PERMANENT TOKEN ALTERED for {pre_qr[1]}! Original: {pre_qr[2]}, New: {post_qr[2]}"
        assert pre_qr[3] == post_qr[3], f"QR status altered for {pre_qr[1]}"
    
    # Check 4: Assignment history remains intact
    post_assignments = post_cur.execute("SELECT id, qr_code_id, business_name, destination_url FROM qr_assignments ORDER BY id").fetchall()
    assert len(post_assignments) == len(pre_assignments), "Assignment count changed"
    for pre_a, post_a in zip(pre_assignments, post_assignments):
        assert pre_a == post_a, f"Assignment record altered: {pre_a} != {post_a}"
    
    # Check 5: Default admin using default password receives must_change_password = True (1)
    admin_row = post_cur.execute("SELECT username, must_change_password, password_hash FROM users WHERE username='admin'").fetchone()
    assert admin_row is not None, "Admin user missing after migration"
    assert admin_row[1] == 1, "Admin user with default password did not receive must_change_password=True"
    
    # Check 6: Existing legitimate operator / custom accounts are not locked out
    op_row = post_cur.execute("SELECT username, must_change_password FROM users WHERE username='operator'").fetchone()
    if op_row:
        assert op_row[1] == 0, "Operator account unnecessarily flagged with must_change_password=True"
    
    # Check 7: Revoked token table is created correctly with all necessary columns
    post_tables = [r[0] for r in post_cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "revoked_tokens" in post_tables, "revoked_tokens table was not created"
    
    revoked_cols = [r[1] for r in post_cur.execute("PRAGMA table_info(revoked_tokens)").fetchall()]
    assert "jti" in revoked_cols, "revoked_tokens missing 'jti' column"
    assert "user_id" in revoked_cols, "revoked_tokens missing 'user_id' column"
    assert "revoked_at" in revoked_cols, "revoked_tokens missing 'revoked_at' column"
    assert "expires_at" in revoked_cols, "revoked_tokens missing 'expires_at' column"
    
    post_conn.close()
