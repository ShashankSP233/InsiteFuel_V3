from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SiteCreate(BaseModel):
    project_id: int

    name: str = Field(
        min_length=1,
        max_length=200,
    )

    site_code: str = Field(
        min_length=1,
        max_length=50,
    )

    is_active: bool = True


class SiteUpdate(BaseModel):
    project_id: int | None = None

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    site_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    is_active: bool | None = None


class SiteResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    project_id: int
    name: str
    site_code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime