from typing import Annotated

from fastapi import Depends

from app.adapters.smtp_sender import SmtpEmailSender
from app.config import settings
from app.ports import EmailSender
from app.services import RoutingService


def get_email_sender() -> EmailSender:
    return SmtpEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        mail_from=settings.mail_from,
        timeout=settings.smtp_timeout,
    )


def get_routing_service(
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> RoutingService:
    return RoutingService(email_sender)
