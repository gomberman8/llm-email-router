import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

from app.exceptions import EmailDeliveryError


class SmtpEmailSender:
    def __init__(self, host: str, port: int, mail_from: str, timeout: int):
        self._host = host
        self._port = port
        self._mail_from = mail_from
        self._timeout = timeout

    def send(self, to: str, subject: str, body: str, reply_to: str) -> str:
        message = EmailMessage()
        message["From"] = self._mail_from
        message["To"] = to
        message["Subject"] = subject
        message["Reply-To"] = reply_to
        message["Message-Id"] = make_msgid()
        message.set_content(body)

        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                smtp.send_message(message)
        except OSError as e:
            raise EmailDeliveryError("Failed to deliver email") from e

        return message["Message-Id"]
