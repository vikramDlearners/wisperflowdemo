"""Email and SMS providers.

Phase 1 uses logging implementations that record every message in an
in-memory outbox instead of sending it. Real SMTP or SMS gateways can be
plugged in later behind the same protocols. Mock is the default.
"""

import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger("carecircle.messaging")


@dataclass
class OutboundMessage:
    channel: str  # "email" or "sms"
    to: str
    subject: str | None
    body: str


class EmailProvider(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class SmsProvider(Protocol):
    def send(self, to: str, body: str) -> None: ...


@dataclass
class LoggingEmailProvider:
    outbox: list[OutboundMessage] = field(default_factory=list)

    def send(self, to: str, subject: str, body: str) -> None:
        self.outbox.append(OutboundMessage("email", to, subject, body))
        logger.info("MOCK EMAIL to=%s subject=%s", to, subject)


@dataclass
class LoggingSmsProvider:
    outbox: list[OutboundMessage] = field(default_factory=list)

    def send(self, to: str, body: str) -> None:
        self.outbox.append(OutboundMessage("sms", to, None, body))
        logger.info("MOCK SMS to=%s", to)


class WhatsAppProvider(Protocol):
    def send(self, to: str, body: str) -> None: ...


@dataclass
class LoggingWhatsAppProvider:
    outbox: list[OutboundMessage] = field(default_factory=list)

    def send(self, to: str, body: str) -> None:
        self.outbox.append(OutboundMessage("whatsapp", to, None, body))
        logger.info("MOCK WHATSAPP to=%s", to)


@dataclass
class SmtpEmailProvider:
    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls()
            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info("SMTP EMAIL sent to=%s subject=%s", to, subject)


_email_provider: EmailProvider = LoggingEmailProvider()
_smtp_email_provider: EmailProvider = SmtpEmailProvider()
_sms_provider: SmsProvider = LoggingSmsProvider()
_whatsapp_provider: WhatsAppProvider = LoggingWhatsAppProvider()


def get_email_provider() -> EmailProvider:
    # Real SMTP when smtp_host is set in .env; otherwise the logging mock.
    if settings.smtp_host:
        return _smtp_email_provider
    return _email_provider


def get_sms_provider() -> SmsProvider:
    # settings.sms_provider is "mock" by default; any other value is not implemented yet.
    if settings.sms_provider != "mock":
        raise NotImplementedError(f"SMS provider '{settings.sms_provider}' is not implemented in Phase 1")
    return _sms_provider


def get_whatsapp_provider() -> WhatsAppProvider:
    # Phase 1: a logging stand-in; a WhatsApp Business API gateway can be plugged in here.
    return _whatsapp_provider
