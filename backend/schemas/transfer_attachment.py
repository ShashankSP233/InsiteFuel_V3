from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TransferAttachmentCreate(BaseModel):
    attachment_id: int


class TransferAttachmentResponse(BaseModel):
    id: int
    transfer_id: int
    attachment_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)