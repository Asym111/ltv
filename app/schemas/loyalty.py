from pydantic import BaseModel


class LoyaltyRunOut(BaseModel):
    status: str


class BirthdayRunOut(BaseModel):
    status: str
    granted: int
