from datetime import datetime
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    phone: str = Field(..., min_length=5, max_length=32)
    full_name: str = Field(default="", max_length=120)
    is_staff: bool = False
    loyalty_tier: str = Field(default="Bronze", max_length=20)


class UserOut(BaseModel):
    id: int
    phone: str
    full_name: str
    is_staff: bool
    loyalty_tier: str
    created_at: datetime

    class Config:
        from_attributes = True
