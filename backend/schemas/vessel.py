from pydantic import BaseModel, ConfigDict, Field


class VesselCreate(BaseModel):
    project_id: int
    name: str = Field(
        min_length=1,
        max_length=150,
    )
    code: str | None = Field(
        default=None,
        max_length=50,
    )


class VesselUpdate(BaseModel):
    project_id: int | None = None
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )
    code: str | None = Field(
        default=None,
        max_length=50,
    )
    is_active: bool | None = None


class VesselResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    code: str | None
    is_active: bool