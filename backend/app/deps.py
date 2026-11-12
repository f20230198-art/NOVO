from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlmodel import Session, select

from .config import settings
from .db import get_session
from .models import User


def optional_user(
    x_user_token: Optional[str] = Header(default=None), session: Session = Depends(get_session)
) -> Optional[User]:
    if not x_user_token:
        return None
    return session.exec(select(User).where(User.token == x_user_token)).first()


def current_user(user: Optional[User] = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Missing or invalid X-User-Token")
    return user


def require_admin(x_admin_key: Optional[str] = Header(default=None)) -> None:
    if not x_admin_key or x_admin_key != settings.admin_key:
        raise HTTPException(status_code=403, detail="Invalid X-Admin-Key")
