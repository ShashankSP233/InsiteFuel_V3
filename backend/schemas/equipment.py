from pydantic import BaseModel, ConfigDict, Field


class EquipmentCreate(BaseModel):
    vessel_id: int
    name: str = Field(
        min_length=1,
        max_length=150,
    )
    equipment_type: str = Field(
        min_length=1,
        max_length=50,
    )
    code: str | None = Field(
        default=None,
        max_length=50,
    )


class EquipmentUpdate(BaseModel):
    vessel_id: int | None = None
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )
    equipment_type: str | None = Field(
        default=None,
        max_length=50,
    )
    code: str | None = Field(
        default=None,
        max_length=50,
    )
    is_active: bool | None = None


class EquipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vessel_id: int
    name: str
    equipment_type: str
    code: str | None
    is_active: bool