from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import (
    verify_password, hash_password, create_access_token,
    get_current_user, get_admin_user
)
from app.models import User, UserRole, AuditLog
from app.schemas import (
    LoginRequest, TokenResponse, UserResponse, PasswordChangeRequest
)
import json

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, req: Request, db: Session = Depends(get_db)):
    """Authenticate user and return JWT token."""
    user = db.query(User).filter(
        User.username == request.username,
        User.is_active == True
    ).first()
    
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    
    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    
    # Audit log
    audit = AuditLog(
        user_id=user.id,
        action="login",
        entity_type="user",
        entity_id=user.id,
        ip_address=req.client.host if req.client else None,
    )
    db.add(audit)
    db.commit()
    
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Logout (client should discard the token)."""
    audit = AuditLog(
        user_id=current_user.id,
        action="logout",
        entity_type="user",
        entity_id=current_user.id,
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
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the current user's password."""
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    
    current_user.password_hash = hash_password(request.new_password)
    
    audit = AuditLog(
        user_id=current_user.id,
        action="password_change",
        entity_type="user",
        entity_id=current_user.id,
    )
    db.add(audit)
    db.commit()
    
    return {"message": "Password changed successfully"}


@router.post("/users", response_model=UserResponse)
async def create_user(
    username: str,
    password: str,
    display_name: str,
    role: str = "operator",
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Create a new user (admin only)."""
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )
    
    user_role = UserRole.ADMIN if role == "admin" else UserRole.OPERATOR
    
    new_user = User(
        username=username,
        password_hash=hash_password(password),
        display_name=display_name,
        role=user_role,
        is_active=True,
    )
    db.add(new_user)
    
    audit = AuditLog(
        user_id=admin.id,
        action="create_user",
        entity_type="user",
        details=json.dumps({"username": username, "role": role}),
    )
    db.add(audit)
    db.commit()
    db.refresh(new_user)
    
    return UserResponse.model_validate(new_user)
