from dataclasses import dataclass
from email.utils import make_msgid


@dataclass
class SentEmail:
    to: str
    subject: str
    body: str
    reply_to: str
    message_id: str


class InMemoryEmailSender:
    def __init__(self) -> None:
        self.sent: list[SentEmail] = []

    def send(self, to: str, subject: str, body: str, reply_to: str) -> str:
        message_id = make_msgid()
        self.sent.append(SentEmail(to, subject, body, reply_to, message_id))
        return message_id
