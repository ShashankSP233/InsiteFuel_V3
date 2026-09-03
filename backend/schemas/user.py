from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    role: str
    full_name: str | None = Field(
        default=None,
        max_length=150,
    )


class UserUpdate(BaseModel):
    username: str | None = Field(
        default=None,
        min_length=3,
        max_length=100,
    )
    role: str | None = None
    full_name: str | None = Field(
        default=None,
        max_length=150,
    )
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(
        min_length=8,
        max_length=128,
    )


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    full_name: str | None
    is_active: bool