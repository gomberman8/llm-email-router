from unittest.mock import patch

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
