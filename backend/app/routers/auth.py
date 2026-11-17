import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import (
    verify_password, hash_password, create_access_token, decode_token,
    get_current_user, get_admin_user, get_super_admin_user, security
)
from app.models import User, UserRole, AuditLog, RevokedToken
from app.schemas import (
    LoginRequest, TokenResponse, UserResponse, PasswordChangeRequest,
    CreateUserRequest, UpdateUserRequest, ResetPasswordRequest
)
from app.config import get_settings
from app.core.limiter import limiter
from app.core.timezone import utc_now, to_ist_str

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit(lambda: get_settings().RATE_LIMIT_AUTH)
async def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user with rate limiting, lockout protection, and credential validation."""
    user = db.query(User).filter(
        User.username == body.username,
        User.is_active == True
    ).first()

    # Check if account is temporarily locked due to brute force attempts
    if user and user.locked_until and user.locked_until > datetime.utcnow():
        lock_remaining = int((user.locked_until - datetime.utcnow()).total_seconds() / 60) + 1
        audit = AuditLog(
            user_id=user.id,
            action="login_locked",
            entity_type="user",
            entity_id=user.id,
            details=json.dumps({"reason": "account_locked", "remaining_minutes": lock_remaining}),
            status="failed",
            ip_address=request.client.host if request.client else None,
        )
        db.add(audit)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Account temporarily locked due to repeated failed attempts. Please try again in {lock_remaining} minutes.",
        )
    
    if not user or not verify_password(body.password, user.password_hash):
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=15)
            db.commit()

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
    
    # Successful login: reset failed attempts & update last login
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()
    db.commit()

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
    current_user.password_changed_at = datetime.utcnow()
    
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


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """List all authorized organizational users (admin only)."""
    users = db.query(User).order_by(User.id.asc()).all()
    return [UserResponse.model_validate(u) for u in users]


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
    
    if body.role == "super_admin":
        user_role = UserRole.SUPER_ADMIN
    elif body.role == "admin":
        user_role = UserRole.ADMIN
    else:
        user_role = UserRole.OPERATOR
    
    new_user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=user_role,
        is_active=True,
        must_change_password=True,
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


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    request: Request,
    body: UpdateUserRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Update user details, active state, or role with protection for the last system owner."""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Safeguard: Prevent disabling or demoting the last active administrator / system owner
    is_admin_role = target_user.role in (UserRole.SUPER_ADMIN, UserRole.ADMIN)
    will_be_inactive = body.is_active is False
    will_be_demoted = body.role is not None and body.role not in ("admin", "super_admin")
    
    if is_admin_role and (will_be_inactive or will_be_demoted):
        other_active_admins = db.query(User).filter(
            User.role.in_([UserRole.SUPER_ADMIN, UserRole.ADMIN]),
            User.is_active == True,
            User.id != target_user.id,
        ).count()
        if other_active_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate or demote the last active System Administrator.",
            )

    if body.display_name is not None:
        target_user.display_name = body.display_name
    if body.is_active is not None:
        target_user.is_active = body.is_active
    if body.role is not None:
        if body.role == "super_admin":
            target_user.role = UserRole.SUPER_ADMIN
        elif body.role == "admin":
            target_user.role = UserRole.ADMIN
        else:
            target_user.role = UserRole.OPERATOR

    target_user.updated_at = datetime.utcnow()
    
    audit = AuditLog(
        user_id=admin.id,
        action="update_user",
        entity_type="user",
        entity_id=target_user.id,
        details=json.dumps({"updated_fields": body.model_dump(exclude_unset=True)}),
        status="success",
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    db.commit()
    db.refresh(target_user)
    return UserResponse.model_validate(target_user)


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    request: Request,
    body: ResetPasswordRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Reset a user's password and enforce mandatory password change on next login."""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    target_user.password_hash = hash_password(body.new_password)
    target_user.must_change_password = True
    target_user.password_changed_at = datetime.utcnow()
    target_user.failed_login_attempts = 0
    target_user.locked_until = None
    
    audit = AuditLog(
        user_id=admin.id,
        action="reset_user_password",
        entity_type="user",
        entity_id=target_user.id,
        details=json.dumps({"target_username": target_user.username}),
        status="success",
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    db.commit()
    return {"message": f"Password reset for user {target_user.username}. Password change required on next login."}


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: int,
    request: Request,
    admin: User = Depends(get_super_admin_user),
    db: Session = Depends(get_db),
):
    """Deactivate user account (Super Admin only). Protected against deleting last admin."""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if target_user.role in (UserRole.SUPER_ADMIN, UserRole.ADMIN):
        other_active_admins = db.query(User).filter(
            User.role.in_([UserRole.SUPER_ADMIN, UserRole.ADMIN]),
            User.is_active == True,
            User.id != target_user.id,
        ).count()
        if other_active_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active System Administrator.",
            )
    
    target_user.is_active = False
    audit = AuditLog(
        user_id=admin.id,
        action="deactivate_user",
        entity_type="user",
        entity_id=target_user.id,
        details=json.dumps({"target_username": target_user.username}),
        status="success",
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    db.commit()
    return {"message": f"User {target_user.username} deactivated successfully"}
    
    return UserResponse.model_validate(new_user)
