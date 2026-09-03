from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=150,
    )
    code: str | None = Field(
        default=None,
        max_length=50,
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
    )


class ProjectUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )
    code: str | None = Field(
        default=None,
        max_length=50,
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
    )
    is_active: bool | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str | None
    description: str | None
    is_active: bool