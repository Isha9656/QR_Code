import secrets
import string
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import QRCode, QRStatus
from app.config import get_settings

settings = get_settings()


def generate_token(length: int = None) -> str:
    """Generate a cryptographically secure random token."""
    length = length or settings.QR_TOKEN_LENGTH
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def get_next_qr_id(db: Session) -> str:
    """Get the next sequential QR ID (e.g., QR-000001)."""
    max_id = db.query(func.max(QRCode.id)).scalar() or 0
    return f"QR-{max_id + 1:06d}"


def bulk_generate_qr_codes(db: Session, quantity: int) -> List[QRCode]:
    """Generate a batch of QR codes with unique tokens."""
    existing_tokens = set(
        t[0] for t in db.query(QRCode.token).all()
    )
    
    qr_codes = []
    max_id = db.query(func.max(QRCode.id)).scalar() or 0
    
    for i in range(quantity):
        # Generate unique token
        token = generate_token()
        attempts = 0
        while token in existing_tokens:
            token = generate_token()
            attempts += 1
            if attempts > 100:
                raise RuntimeError("Unable to generate unique token after 100 attempts")
        
        existing_tokens.add(token)
        qr_id = f"QR-{max_id + i + 1:06d}"
        
        qr_code = QRCode(
            qr_id=qr_id,
            token=token,
            status=QRStatus.UNASSIGNED,
        )
        qr_codes.append(qr_code)
    
    db.add_all(qr_codes)
    db.commit()
    
    # Refresh to get IDs
    for qr in qr_codes:
        db.refresh(qr)
    
    return qr_codes


def get_qr_redirect_url(token: str) -> str:
    """Build the permanent redirect URL for a QR code."""
    return f"{settings.BASE_URL}/q/{token}"
