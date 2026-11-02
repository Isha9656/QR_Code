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


def init_db():
    """Create all tables and perform lightweight schema migrations."""
    import app.models  # Ensure all models are registered on Base.metadata
    from sqlalchemy import text
    Base.metadata.create_all(bind=engine)
    
    # Run column migrations for SQLite
    if settings.DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            # Check users table
            user_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(users)"))]
            if "must_change_password" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0"))
                conn.commit()
            
            # Check audit_logs table
            audit_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(audit_logs)"))]
            if "status" not in audit_cols:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'success'"))
                conn.commit()

