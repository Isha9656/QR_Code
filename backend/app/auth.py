import uuid
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import get_db
from app.models import User, UserRole, RevokedToken

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token with a unique jti identifier and iat timestamp."""
    to_encode = data.copy()
    now_utc = datetime.utcnow()
    expire = now_utc + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    jti = uuid.uuid4().hex
    to_encode.update({"exp": expire, "jti": jti, "iat": int(now_utc.timestamp())})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Get the current authenticated user from the JWT token with persistent revocation check and password change enforcement."""
    raw_token = None
    if credentials is not None:
        raw_token = credentials.credentials
    elif "token" in request.query_params:
        raw_token = request.query_params["token"]

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_token(raw_token)
    
    # Check persistent token revocation
    jti = payload.get("jti")
    if jti:
        revoked = db.query(RevokedToken).filter(RevokedToken.jti == jti).first()
        if revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    
    if str(user_id).isdigit():
        user = db.query(User).filter(User.id == int(user_id), User.is_active == True).first()
    else:
        user = db.query(User).filter(User.username == str(user_id), User.is_active == True).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Check session invalidation from password changes
    if user.password_changed_at:
        token_iat = payload.get("iat")
        if token_iat:
            # Allow 2 seconds grace for clock skew
            if token_iat < int(user.password_changed_at.timestamp()) - 2:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session expired due to password change. Please log in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

    # Centralized password change enforcement
    if user.must_change_password:
        path = request.url.path.rstrip("/")
        allowed_paths = (
            "/api/auth/change-password",
            "/api/auth/logout",
            "/api/auth/me",
        )
        if path not in allowed_paths:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Password change required. You must change your default password before accessing the system.",
                headers={"X-Require-Password-Change": "true"},
            )

    return user


async def get_super_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Require Super Admin (System Owner) role."""
    if current_user.role not in (UserRole.SUPER_ADMIN, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin / System Owner access required",
        )
    return current_user


async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Require Admin or Super Admin role."""
    if current_user.role not in (UserRole.SUPER_ADMIN, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Optionally get the current user (returns None if not authenticated)."""
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        jti = payload.get("jti")
        if jti:
            revoked = db.query(RevokedToken).filter(RevokedToken.jti == jti).first()
            if revoked:
                return None
        user_id = payload.get("sub")
        if user_id is None:
            return None
        user = db.query(User).filter(User.id == int(user_id), User.is_active == True).first()
        return user
    except HTTPException:
        return None


def create_default_admin(db: Session):
    """Create a default admin user if none exists and set must_change_password."""
    admin = db.query(User).filter(User.username == "admin").first()
    if admin is None:
        admin = User(
            username="admin",
            password_hash=hash_password("admin123"),
            display_name="System Administrator",
            role=UserRole.ADMIN,
            is_active=True,
            must_change_password=True,
        )
        db.add(admin)
        db.commit()
        print("[!] Default admin created with mandatory password change requirement.")
    elif verify_password("admin123", admin.password_hash) and not admin.must_change_password:
        admin.must_change_password = True
        db.commit()
        print("[!] Existing admin is using default password; must_change_password flag set.")
