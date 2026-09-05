import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.session import Session as UserSession
from backend.models.user import User
from backend.services.audit_service import AuditService

password_hash = PasswordHash.recommended()

SESSION_DURATION_HOURS = 12


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(
    password: str,
    password_hash_value: str,
) -> bool:
    return password_hash.verify(
        password,
        password_hash_value,
    )


def hash_session_token(token: str) -> str:
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def create_session(
    db: Session,
    user: User,
) -> tuple[str, UserSession]:
    """
    Create a new authenticated session.

    The raw token is returned to the client.
    Only its SHA-256 hash is stored in the database.
    """

    raw_token = secrets.token_urlsafe(48)
    token_hash = hash_session_token(raw_token)

    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=SESSION_DURATION_HOURS
    )

    user_session = UserSession(
        session_token=token_hash,
        user_id=user.id,
        expires_at=expires_at,
    )

    db.add(user_session)
    db.flush()

    return raw_token, user_session


def get_session(
    db: Session,
    raw_token: str,
) -> UserSession | None:
    token_hash = hash_session_token(raw_token)

    return db.scalar(
        select(UserSession).where(
            UserSession.session_token == token_hash,
        )
    )


def delete_session(
    db: Session,
    raw_token: str,
) -> bool:
    user_session = get_session(db, raw_token)

    if user_session is None:
        return False

    db.delete(user_session)
    db.flush()

    return True


def reset_password(
    db: Session,
    user: User,
    new_password: str,
    reset_by_user_id: int | None = None,
) -> None:
    if len(new_password) < 8:
        raise ValueError(
            "Password must be at least 8 characters."
        )

    user.password_hash = hash_password(new_password)

    # Revoke all existing sessions for this user.
    sessions = db.scalars(
        select(UserSession).where(
            UserSession.user_id == user.id
        )
    ).all()

    for user_session in sessions:
        db.delete(user_session)

    db.flush()
    AuditService.log(
        db=db,
        user_id=reset_by_user_id,
        action="RESET_USER_PASSWORD",
        entity="users",
        entity_id=user.id,
        old_values=None,
        new_values={
            "password_reset": True,
            "active_sessions_revoked": True,
        },
        details="User password reset and existing sessions revoked.",
    )