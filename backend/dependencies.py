from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.session import Session as UserSession
from backend.models.user import User, UserRole
from backend.services.auth_service import get_session

security = HTTPBearer()

def db_session():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def get_authenticated_session(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(db_session),
) -> tuple[User, UserSession]:

    token = credentials.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token.",
        )

    user_session = get_session(db, token)

    if user_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session.",
        )

    if user_session.expires_at <= datetime.now(timezone.utc):
        db.delete(user_session)
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired.",
        )

    user = db.get(User, user_session.user_id)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive or no longer exists.",
        )

    return user, user_session


def get_current_user(
    authenticated: tuple[User, UserSession] = Depends(
        get_authenticated_session
    ),
) -> User:
    user, _ = authenticated
    return user


def require_roles(*allowed_roles: UserRole):

    def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:

        # ADMIN has unrestricted access.
        if current_user.role == UserRole.ADMIN.value:
            return current_user

        allowed_values = {
            role.value
            for role in allowed_roles
        }

        if current_user.role not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )

        return current_user

    return dependency