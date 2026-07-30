from app.agent.agent import RoutingResult, route_message
from app.ports import EmailSender


class RoutingService:
    def __init__(self, email_sender: EmailSender):
        self._email_sender = email_sender

    async def route(self, sender_email: str, message: str) -> RoutingResult:
        return await route_message(message, sender_email, self._email_sender)
