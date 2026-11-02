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


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(default="operator")


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
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

class AssignRequest(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=200)
    destination_url: str = Field(..., min_length=1)
    notes: Optional[str] = None
    expiry_date: Optional[datetime] = None

    @field_validator("destination_url")
    @classmethod
    def validate_url(cls, v):
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Only HTTP and HTTPS URLs are allowed")
        if not parsed.netloc:
            raise ValueError("Invalid URL: missing domain")
        return v


class ReassignRequest(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=200)
    destination_url: str = Field(..., min_length=1)
    notes: Optional[str] = None
    expiry_date: Optional[datetime] = None
    confirm_reassignment: bool = Field(..., description="Must be True to confirm reassignment")

    @field_validator("destination_url")
    @classmethod
    def validate_url(cls, v):
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Only HTTP and HTTPS URLs are allowed")
        if not parsed.netloc:
            raise ValueError("Invalid URL: missing domain")
        return v


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

