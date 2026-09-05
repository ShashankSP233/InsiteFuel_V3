from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.user import User, UserRole
from backend.services.auth_service import hash_password
from backend.services.audit_service import AuditService





def get_user_by_username(
    db: Session,
    username: str,
) -> User | None:
    return db.scalar(
        select(User).where(
            User.username == username
        )
    )


def create_user(
    db: Session,
    username: str,
    password: str,
    role: str,
    full_name: str | None = None,
    created_by_user_id: int | None = None,
) -> User:
    username = username.strip()

    if not username:
        raise ValueError("Username cannot be empty.")

    role = role.upper()

    if role not in (
        UserRole.ADMIN.value,
        UserRole.MANAGER.value,
        UserRole.OPERATOR.value,
    ):
        raise ValueError(
            "Invalid role. "
            "Role must be ADMIN, MANAGER, or OPERATOR."
        )

    existing_user = get_user_by_username(
        db,
        username,
    )

    if existing_user is not None:
        raise ValueError(
            f"Username '{username}' already exists."
        )

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        full_name=full_name,
        is_active=True,
    )

    db.add(user)
    db.flush()
    AuditService.log(
        db=db,
        user_id=created_by_user_id,
        action="CREATE_USER",
        entity="users",
        entity_id=user.id,
        old_values=None,
        new_values={
            "username": user.username,
            "role": user.role,
            "full_name": user.full_name,
            "is_active": user.is_active,
        },
        details="User account created.",
    )
    return user


def get_user_by_id(
    db: Session,
    user_id: int,
) -> User | None:
    return db.get(User, user_id)


def update_user(
    db: Session,
    user: User,
    *,
    username: str | None = None,
    role: str | None = None,
    full_name: str | None = None,
    is_active: bool | None = None,
    updated_by_user_id: int | None = None,
) -> User:
    old_values = {
        "username": user.username,
        "role": user.role,
        "full_name": user.full_name,
        "is_active": user.is_active,
    }
    if username is not None:
        username = username.strip()

        if not username:
            raise ValueError(
                "Username cannot be empty."
            )

        existing_user = get_user_by_username(
            db,
            username,
        )

        if (
            existing_user is not None
            and existing_user.id != user.id
        ):
            raise ValueError(
                f"Username '{username}' already exists."
            )

        user.username = username

    if role is not None:
        role = role.upper()

        if role not in (
            UserRole.ADMIN.value,
            UserRole.MANAGER.value,
            UserRole.OPERATOR.value,
        ):
            raise ValueError(
                "Invalid role. "
                "Role must be ADMIN, MANAGER, or OPERATOR."
            )

        user.role = role

    if full_name is not None:
        user.full_name = full_name

    if is_active is not None:
        user.is_active = is_active

    db.flush()
    new_values = {
    "username": user.username,
    "role": user.role,
    "full_name": user.full_name,
    "is_active": user.is_active,
    }

    AuditService.log(
        db=db,
        user_id=updated_by_user_id,
        action="UPDATE_USER",
        entity="users",
        entity_id=user.id,
        old_values=old_values,
        new_values=new_values,
        details="User account updated.",
    )
    return user