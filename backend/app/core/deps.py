"""Shared FastAPI dependencies: current user + role guards."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import get_db
from app.models import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    cred_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except Exception:
        raise cred_error
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise cred_error
    return user


def require_roles(*roles: UserRole):
    def guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return guard


# Convenience guards
require_coordinator = require_roles(UserRole.admin, UserRole.coordinator)
require_staff = require_roles(UserRole.admin, UserRole.coordinator, UserRole.instructor)
