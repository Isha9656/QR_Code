import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import (
    verify_password, hash_password, create_access_token, decode_token,
    get_current_user, get_admin_user, security
)
from app.models import User, UserRole, AuditLog, RevokedToken
from app.schemas import (
    LoginRequest, TokenResponse, UserResponse, PasswordChangeRequest, CreateUserRequest
)
from app.config import get_settings
from app.core.limiter import limiter
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit(lambda: get_settings().RATE_LIMIT_AUTH)
async def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user, return JWT token with unique jti, and check must_change_password."""
    user = db.query(User).filter(
        User.username == body.username,
        User.is_active == True
    ).first()
    
    if not user or not verify_password(body.password, user.password_hash):
        # Audit log failed login without exposing password
        audit = AuditLog(
            user_id=user.id if user else None,
            action="login_failed",
            entity_type="user",
            entity_id=user.id if user else None,
            details=json.dumps({"attempted_username": body.username}),
            status="failed",
            ip_address=request.client.host if request.client else None,
        )
        db.add(audit)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    
    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    
    # Audit successful login
    audit = AuditLog(
        user_id=user.id,
        action="login",
        entity_type="user",
        entity_id=user.id,
        status="success",
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    db.commit()
    
    return TokenResponse(
        access_token=token,
        must_change_password=user.must_change_password,
        user=UserResponse.model_validate(user),
    )


@router.post("/logout")
async def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Logout and revoke the JWT token persistently across server restarts."""
    if credentials and credentials.credentials:
        try:
            payload = decode_token(credentials.credentials)
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                expires_at = datetime.utcfromtimestamp(exp)
                existing = db.query(RevokedToken).filter(RevokedToken.jti == jti).first()
                if not existing:
                    revoked = RevokedToken(
                        jti=jti,
                        user_id=current_user.id,
                        expires_at=expires_at,
                    )
                    db.add(revoked)
        except Exception:
            pass

    audit = AuditLog(
        user_id=current_user.id,
        action="logout",
        entity_type="user",
        entity_id=current_user.id,
        status="success",
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    db.commit()
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return UserResponse.model_validate(current_user)


@router.post("/change-password")
async def change_password(
    request: Request,
    body: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the current user's password and clear must_change_password flag."""
    if not verify_password(body.current_password, current_user.password_hash):
        audit = AuditLog(
            user_id=current_user.id,
            action="password_change_failed",
            entity_type="user",
            entity_id=current_user.id,
            status="failed",
            details=json.dumps({"reason": "incorrect_current_password"}),
            ip_address=request.client.host if request.client else None,
        )
        db.add(audit)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    
    # Disallow reusing default password
    if body.new_password == "admin123":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password cannot be the default password. Please choose a unique strong password.",
        )
    
    current_user.password_hash = hash_password(body.new_password)
    current_user.must_change_password = False
    
    audit = AuditLog(
        user_id=current_user.id,
        action="password_change",
        entity_type="user",
        entity_id=current_user.id,
        status="success",
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    db.commit()
    
    return {"message": "Password changed successfully", "must_change_password": False}


@router.post("/users", response_model=UserResponse)
async def create_user(
    request: Request,
    body: CreateUserRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Create a new user (admin only). Accepts JSON body."""
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )
    
    user_role = UserRole.ADMIN if body.role == "admin" else UserRole.OPERATOR
    
    new_user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=user_role,
        is_active=True,
        must_change_password=False,
    )
    db.add(new_user)
    
    audit = AuditLog(
        user_id=admin.id,
        action="create_user",
        entity_type="user",
        details=json.dumps({"username": body.username, "role": body.role}),
        status="success",
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    db.commit()
    db.refresh(new_user)
    
    return UserResponse.model_validate(new_user)
