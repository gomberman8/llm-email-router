from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

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


class RouteResponse(BaseModel):
    department: str
    message_id: str
    routed_by: Literal["agent", "fallback"]
    processing_time_ms: int
