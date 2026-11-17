from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings

settings = get_settings()

# Handle SQLite specific connect args
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(target_engine=None):
    """Create all tables and perform lightweight schema migrations."""
    import app.models  # Ensure all models are registered on Base.metadata
    from sqlalchemy import text
    eng = target_engine or engine
    Base.metadata.create_all(bind=eng)
    
    # Run column migrations for SQLite
    with eng.connect() as conn:
        # Check users table
        user_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(users)"))]
        if "must_change_password" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0"))
            conn.commit()
        if "failed_login_attempts" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0"))
            conn.commit()
        if "locked_until" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN locked_until TIMESTAMP NULL"))
            conn.commit()
        if "last_login_at" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP NULL"))
            conn.commit()
        if "password_changed_at" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMP NULL"))
            conn.commit()
        if "mfa_enabled" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN NOT NULL DEFAULT 0"))
            conn.commit()
        if "mfa_secret" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN mfa_secret VARCHAR(64) NULL"))
            conn.commit()
        
        # Check audit_logs table
        audit_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(audit_logs)"))]
        if "status" not in audit_cols:
            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'success'"))
            conn.commit()
        
        # Performance indexes for client-wise aggregations and scan analytics
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_qr_codes_current_business_name ON qr_codes (current_business_name)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_qr_assignments_business_name ON qr_assignments (business_name)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_scan_events_qr_result_scanned ON qr_scan_events (qr_code_id, result_type, scanned_at)"))
        conn.commit()

