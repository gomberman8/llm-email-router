from typing import Protocol


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str, reply_to: str) -> str: ...
