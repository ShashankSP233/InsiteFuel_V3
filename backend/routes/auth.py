from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import db_session, get_current_user
from backend.models.user import User
from backend.services.auth_service import (
    create_session,
    delete_session,
    verify_password,
)
from backend.services.user_service import get_user_by_username

from backend.dependencies import (
    db_session,
    get_authenticated_session,
    get_current_user,
)
from backend.models.session import Session as UserSession

router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    session_token: str
    expires_at: str
    user_id: int
    username: str
    role: str
    full_name: str | None


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(db_session),
):
    user = get_user_by_username(
        db,
        payload.username.strip(),
    )

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    if not verify_password(
        payload.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    session_token, user_session = create_session(
        db,
        user,
    )

    db.commit()

    return LoginResponse(
        session_token=session_token,
        expires_at=user_session.expires_at.isoformat(),
        user_id=user.id,
        username=user.username,
        role=user.role,
        full_name=user.full_name,
    )


@router.post("/logout")
def logout(
    authenticated: tuple[User, UserSession] = Depends(
        get_authenticated_session
    ),
    db: Session = Depends(db_session),
):
    _, user_session = authenticated

    db.delete(user_session)
    db.commit()

    return {
        "message": "Logged out successfully."
    }

@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user),
):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "full_name": current_user.full_name,
        "is_active": current_user.is_active,
    }