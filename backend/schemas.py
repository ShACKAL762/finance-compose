from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TransactionCreate(BaseModel):
    date: date
    type: Literal["income", "expense"]
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=255)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


    @field_validator("category", "description", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class TransactionResponse(TransactionCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)