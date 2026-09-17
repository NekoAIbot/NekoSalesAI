"""Nera notification layer.

Provides unified access to:
- Email (SMTP via app.mail.transport)
- SMS (Brevo API via app.notify.sms)
"""

from app.notify.sms import send_sms, get_sms_provider, SmsResult

__all__ = ["send_sms", "get_sms_provider", "SmsResult"]
