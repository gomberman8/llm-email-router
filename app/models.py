from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.config import settings


class RouteRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "pracownik@firma.pl",
                "message": "Nie działa mi drukarka od rana.",
            }
        }
    )

    email: EmailStr
    message: str = Field(max_length=settings.max_message_chars)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty or whitespace-only")
        return value


class RouteResponse(BaseModel):
    department: str
    message_id: str
    routed_by: Literal["agent", "fallback"]
    processing_time_ms: int
