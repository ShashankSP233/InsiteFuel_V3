from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.user import User, UserRole
from backend.services.auth_service import hash_password

from backend.models.user import User, UserRole



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
) -> User:

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

    return user