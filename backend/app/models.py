import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Enum, ForeignKey,
    Boolean, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"


class QRStatus(str, enum.Enum):
    UNASSIGNED = "unassigned"
    ACTIVE = "active"
    DISABLED = "disabled"
    RETIRED = "retired"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.OPERATOR)
    is_active = Column(Boolean, default=True, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    assignments = relationship("QRAssignment", back_populates="assigned_by_user", foreign_keys="QRAssignment.assigned_by")
    audit_logs = relationship("AuditLog", back_populates="user")


class QRCode(Base):
    __tablename__ = "qr_codes"

    id = Column(Integer, primary_key=True, index=True)
    qr_id = Column(String(20), unique=True, nullable=False, index=True)  # QR-000001
    token = Column(String(64), unique=True, nullable=False, index=True)  # Random secure token
    status = Column(Enum(QRStatus), nullable=False, default=QRStatus.UNASSIGNED, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Current active assignment (denormalized for fast lookups)
    current_destination = Column(Text, nullable=True)
    current_business_name = Column(String(200), nullable=True)

    # Relationships
    assignments = relationship("QRAssignment", back_populates="qr_code", order_by="QRAssignment.assigned_at.desc()")
    scan_events = relationship("QRScanEvent", back_populates="qr_code", order_by="QRScanEvent.scanned_at.desc()")

    __table_args__ = (
        Index("ix_qr_codes_status_created", "status", "created_at"),
        Index("ix_qr_codes_current_business_name", "current_business_name"),
    )


class QRAssignment(Base):
    __tablename__ = "qr_assignments"

    id = Column(Integer, primary_key=True, index=True)
    qr_code_id = Column(Integer, ForeignKey("qr_codes.id"), nullable=False, index=True)
    business_name = Column(String(200), nullable=False)
    destination_url = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    assigned_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    deactivated_at = Column(DateTime, nullable=True)
    deactivated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    expiry_date = Column(DateTime, nullable=True)

    # Relationships
    qr_code = relationship("QRCode", back_populates="assignments")
    assigned_by_user = relationship("User", back_populates="assignments", foreign_keys=[assigned_by])
    deactivated_by_user = relationship("User", foreign_keys=[deactivated_by])

    __table_args__ = (
        # Only one active assignment per QR code
        Index("ix_qr_assignments_active", "qr_code_id", "is_active",
              unique=True,
              sqlite_where=Column("is_active") == True),
        Index("ix_qr_assignments_business_name", "business_name"),
    )


class QRScanEvent(Base):
    __tablename__ = "qr_scan_events"

    id = Column(Integer, primary_key=True, index=True)
    qr_code_id = Column(Integer, ForeignKey("qr_codes.id"), nullable=False, index=True)
    scanned_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    result_type = Column(String(20), nullable=False)  # redirect, unassigned, disabled, retired
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)

    # Relationships
    qr_code = relationship("QRCode", back_populates="scan_events")

    __table_args__ = (
        Index("ix_scan_events_date", "scanned_at"),
        Index("ix_scan_events_qr_result_scanned", "qr_code_id", "result_type", "scanned_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)  # qr_code, assignment, user
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)  # JSON string with action details
    status = Column(String(20), default="success", nullable=False, index=True)  # success, failed
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_action_status", "action", "status"),
        Index("ix_audit_logs_created_at", "created_at"),
    )


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    revoked_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)

