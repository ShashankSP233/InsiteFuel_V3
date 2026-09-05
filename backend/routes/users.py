from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.dependencies import (
    db_session,
    require_roles,
)
from backend.models.user import User, UserRole
from backend.schemas.user import (
    PasswordReset,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from backend.services.auth_service import reset_password
from backend.services.user_service import (
    create_user,
    get_user_by_id,
    update_user,
)


router = APIRouter(
    prefix="/api/users",
    tags=["Users"],
)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_new_user(
    payload: UserCreate,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN)
    ),
):
    try:
        user = create_user(
            db=db,
            username=payload.username,
            password=payload.password,
            role=payload.role,
            full_name=payload.full_name,
            created_by_user_id=current_user.id,
        )

        db.commit()
        db.refresh(user)

        return user

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "",
    response_model=list[UserResponse],
)
def list_users(
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN)
    ),
):
    return db.scalars(
        select(User).order_by(User.id)
    ).all()


@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
def get_user(
    user_id: int,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN)
    ),
):
    user = get_user_by_id(db, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return user


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
)
def update_existing_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN)
    ),
):
    user = get_user_by_id(db, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    # Prevent accidentally locking yourself out.
    if (
        user.id == current_user.id
        and payload.is_active is False
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account.",
        )

    try:
        user = update_user(
            db,
            user,
            username=payload.username,
            role=payload.role,
            full_name=payload.full_name,
            is_active=payload.is_active,
            updated_by_user_id=current_user.id,
        )

        db.commit()
        db.refresh(user)

        return user

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/{user_id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
)
def reset_user_password(
    user_id: int,
    payload: PasswordReset,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN)
    ),
):
    user = get_user_by_id(db, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    try:
        reset_password(
            db,
            user,
            payload.new_password,
            reset_by_user_id=current_user.id,
        )

        db.commit()

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return None