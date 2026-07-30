from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.config import settings


class RouteRequest(BaseModel):
    email: EmailStr
    message: str = Field(max_length=settings.max_message_chars)


class RouteResponse(BaseModel):
    department: str
    reasoning: str
    message_id: str
    routed_by: Literal["agent", "fallback"]
    processing_time_ms: int
