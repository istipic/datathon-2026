"""E-mail sending via SMTP (Mailpit in dev) and per-app Jinja2 templates."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from opendata_core.config import CoreSettings

STARTTLS_PORT = 587


def make_template_env(templates_dir: Path) -> Environment:
    """Jinja2 environment for an app's e-mail templates (HTML auto-escaped)."""
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_email(env: Environment, template: str, /, **context: Any) -> str:
    """Render ``template`` with ``context`` (any variable name is allowed in the context)."""
    return env.get_template(template).render(**context)


def send_email(to: str, subject: str, html: str, text: str, *, settings: CoreSettings) -> None:
    """Send a multipart (text + HTML) message. Uses STARTTLS when the port is 587.

    Credentials are only used when ``smtp_user`` is set and are never logged.
    """
    if any(c in value for value in (to, subject) for c in "\r\n"):
        raise ValueError("header injection attempt: newline in recipient or subject")
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(
        settings.smtp_host, settings.smtp_port, timeout=settings.http_timeout_s
    ) as smtp:
        if settings.smtp_port == STARTTLS_PORT:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
