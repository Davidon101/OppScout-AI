"""Email through Brevo's HTTPS API.

Render's free tier blocks SMTP ports, so mail is sent as a normal web request.
Standard library only. The API key is read from settings and never logged.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from email.utils import parseaddr

log = logging.getLogger(__name__)
URL = "https://api.brevo.com/v3/smtp/email"


class BrevoEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, opener=None, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self._open = opener or urllib.request.urlopen

    def _payload(self, message):
        name, address = parseaddr(message.from_email or settings.DEFAULT_FROM_EMAIL)
        payload = {
            "sender": {"name": name or settings.BREVO_SENDER_NAME, "email": settings.BREVO_SENDER_EMAIL or address},
            "to": [{"email": a} for a in message.to],
            "subject": message.subject,
        }
        html = next((c for c, mime in getattr(message, "alternatives", []) if mime == "text/html"), None)
        if html:
            payload["htmlContent"] = html
            payload["textContent"] = message.body
        elif message.content_subtype == "html":
            payload["htmlContent"] = message.body
        else:
            payload["textContent"] = message.body
        return payload

    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            if not message.to:
                continue
            request = urllib.request.Request(
                URL,
                data=json.dumps(self._payload(message)).encode("utf-8"),
                headers={"api-key": settings.BREVO_API_KEY, "Content-Type": "application/json", "accept": "application/json"},
                method="POST",
            )
            try:
                with self._open(request, timeout=15):
                    sent += 1
            except (urllib.error.URLError, OSError, ValueError) as exc:
                code = getattr(exc, "code", "")
                log.error("Brevo send failed (%s %s)", type(exc).__name__, code)
                if not self.fail_silently:
                    raise
        return sent
