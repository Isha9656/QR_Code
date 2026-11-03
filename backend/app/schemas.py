import re
import ipaddress
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from urllib.parse import urlparse


# ---- Auth Schemas ----

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?/`~" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(default="operator")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?/`~" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    must_change_password: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool = False
    user: UserResponse


# ---- QR Schemas ----

class BulkGenerateRequest(BaseModel):
    quantity: int = Field(..., ge=1, le=5000)


class QRCodeResponse(BaseModel):
    id: int
    qr_id: str
    token: str
    status: str
    current_destination: Optional[str] = None
    current_business_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    redirect_url: Optional[str] = None

    class Config:
        from_attributes = True


class QRCodeListResponse(BaseModel):
    items: List[QRCodeResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


# ---- Assignment Schemas ----

def _validate_destination_url_security(v: str) -> str:
    """Harden URL validation to permit public domains and public IPs while blocking SSRF/metadata/loopback/unsafe schemes."""
    if not v or not isinstance(v, str):
        raise ValueError("Destination URL must be a non-empty string")
    v = v.strip()
    if any(c.isspace() for c in v):
        raise ValueError("URL cannot contain whitespace")
    parsed = urlparse(v)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError("Only HTTP and HTTPS URLs are allowed")
    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not allowed")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: missing domain or hostname")
    
    # Check if hostname is an IP address
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_loopback:
            raise ValueError(f"Loopback IP address '{hostname}' is not permitted")
        if ip.is_link_local:
            raise ValueError(f"Link-local / cloud metadata IP address '{hostname}' is not permitted")
        if ip.is_unspecified:
            raise ValueError(f"Unspecified IP address '{hostname}' is not permitted")
        if str(ip) in {"169.254.169.254", "0.0.0.0"}:
            raise ValueError(f"Destination IP '{hostname}' is not permitted")
    except ValueError as e:
        if "not permitted" in str(e):
            raise
        # Not a valid IP, so it must be a regular domain/hostname
        if not re.match(r"^[a-zA-Z0-9.-]+$", hostname):
            raise ValueError("Invalid hostname: contains disallowed characters")
        if hostname.startswith(".") or hostname.endswith(".") or ".." in hostname:
            raise ValueError("Invalid hostname: improper domain structure")
    return v


class AssignRequest(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=200)
    destination_url: str = Field(..., min_length=1)
    notes: Optional[str] = None
    expiry_date: Optional[datetime] = None

    @field_validator("destination_url")
    @classmethod
    def validate_url(cls, v):
        return _validate_destination_url_security(v)


class ReassignRequest(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=200)
    destination_url: str = Field(..., min_length=1)
    notes: Optional[str] = None
    expiry_date: Optional[datetime] = None
    confirm_reassignment: bool = Field(..., description="Must be True to confirm reassignment")

    @field_validator("destination_url")
    @classmethod
    def validate_url(cls, v):
        return _validate_destination_url_security(v)


class AssignmentResponse(BaseModel):
    id: int
    qr_code_id: int
    business_name: str
    destination_url: str
    notes: Optional[str] = None
    is_active: bool
    assigned_by: int
    assigned_by_name: Optional[str] = None
    assigned_at: datetime
    deactivated_at: Optional[datetime] = None
    deactivated_by: Optional[int] = None
    deactivated_by_name: Optional[str] = None
    expiry_date: Optional[datetime] = None

    class Config:
        from_attributes = True


class AssignmentHistoryResponse(BaseModel):
    qr_id: str
    qr_status: str
    assignments: List[AssignmentResponse]


# ---- QR Resolve (Public) ----

class QRResolveResponse(BaseModel):
    status: str
    qr_id: Optional[str] = None
    destination_url: Optional[str] = None
    business_name: Optional[str] = None
    message: Optional[str] = None


# ---- Analytics ----

class AnalyticsOverview(BaseModel):
    total_qr_codes: int
    unassigned: int
    active: int
    disabled: int
    retired: int
    total_scans: int
    scans_today: int
    scans_this_week: int
    scans_this_month: int


class ScanEventResponse(BaseModel):
    id: int
    qr_code_id: int
    qr_id: Optional[str] = None
    scanned_at: datetime
    result_type: str

    class Config:
        from_attributes = True


class ScanListResponse(BaseModel):
    items: List[ScanEventResponse]
    total: int
    page: int
    per_page: int


# ---- Print Schemas ----

class PrintRequest(BaseModel):
    qr_ids: List[int] = Field(..., min_length=1)
    qr_size_mm: int = Field(default=30, ge=15, le=80)
    show_labels: bool = True
    show_logo: bool = False
    page_margin_mm: int = Field(default=10, ge=5, le=30)
    spacing_mm: int = Field(default=5, ge=2, le=20)


class PrintStudioRequest(BaseModel):
    quantity: Optional[int] = Field(default=None, ge=1, le=2000)
    qr_ids: Optional[List[int]] = None
    qr_size_mm: int = Field(default=30, ge=15, le=80)
    show_labels: bool = True
    company_name: Optional[str] = "INTERNAL QR MANAGEMENT"
    header_text: Optional[str] = "OFFICIAL ASSET STICKERS • DO NOT DISCARD"
    footer_text: Optional[str] = "Scan with internal system camera to activate or reassign"
    page_margin_mm: int = Field(default=10, ge=5, le=30)
    spacing_mm: int = Field(default=5, ge=2, le=20)
    custom_rows: Optional[int] = Field(default=None, ge=1, le=20)
    custom_cols: Optional[int] = Field(default=None, ge=1, le=10)
    unassigned_only: bool = True


class PrintStudioPreviewResponse(BaseModel):
    total_qrs: int
    unassigned_available: int
    qr_size_mm: int
    cols: int
    rows: int
    qrs_per_page: int
    total_pages: int
    page_margin_mm: int
    spacing_mm: int
    company_name: Optional[str] = None
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    sample_qrs: List[dict] = []


class QRInventoryStats(BaseModel):
    total: int
    unassigned: int
    active: int
    disabled: int
    retired: int


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    details: Optional[str] = None
    status: str = "success"
    ip_address: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


