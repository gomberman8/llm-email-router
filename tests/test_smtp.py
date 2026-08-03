from email.utils import parseaddr
from unittest.mock import MagicMock, patch

from app.adapters.smtp_sender import SmtpEmailSender
from app.exceptions import EmailDeliveryError


def test_smtp_sender_wraps_oserror_in_email_delivery_error():
    sender = SmtpEmailSender("localhost", 1025, "from@x.com", 5)
    with patch("smtplib.SMTP", side_effect=OSError("connection refused")):
        try:
            sender.send("to@x.com", "Subject", "Body", "reply@x.com")
        except EmailDeliveryError:
            pass
        else:
            raise AssertionError("EmailDeliveryError was not raised")


def _capture_sent_message(reply_to: str = "jan.nowak@example.com"):
    sender = SmtpEmailSender("localhost", 1025, "router@example.com", 5)
    smtp = MagicMock()
    with patch("smtplib.SMTP") as smtp_cls:
        smtp_cls.return_value.__enter__.return_value = smtp
        sender.send("kadry@example.com", "Wniosek urlopowy", "Body", reply_to)
    return smtp.send_message.call_args.args[0]


def test_from_header_names_the_sender_but_keeps_the_router_address():
    message = _capture_sent_message()

    display, address = parseaddr(message["From"])
    assert display == "jan.nowak@example.com via LLM Router"
    assert address == "router@example.com"
    assert message["Reply-To"] == "jan.nowak@example.com"
