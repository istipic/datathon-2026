from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pytest

from opendata_core import email as mail
from opendata_core.config import CoreSettings


class FakeSMTP:
    instances: list[FakeSMTP] = []

    def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
        self.host, self.port = host, port
        self.started_tls = False
        self.login_args: tuple[str, str] | None = None
        self.sent: list[EmailMessage] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, user: str, password: str) -> None:
        self.login_args = (user, password)

    def send_message(self, msg: EmailMessage) -> None:
        self.sent.append(msg)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSMTP]:
    FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


def _settings(**kw: Any) -> CoreSettings:
    return CoreSettings(_env_file=None, smtp_from="no-reply@blizu.test", **kw)  # type: ignore[call-arg]


def test_send_plain_dev_smtp_no_tls_no_login() -> None:
    mail.send_email("a@b.hr", "Pozdrav", "<p>Bok</p>", "Bok", settings=_settings(smtp_port=1025))
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("127.0.0.1", 1025)
    assert not smtp.started_tls
    assert smtp.login_args is None
    msg = smtp.sent[0]
    assert msg["To"] == "a@b.hr"
    assert msg["From"] == "no-reply@blizu.test"
    assert msg["Subject"] == "Pozdrav"
    assert msg.get_body(("plain",)).get_content().strip() == "Bok"  # type: ignore[union-attr]
    assert "<p>Bok</p>" in msg.get_body(("html",)).get_content()  # type: ignore[union-attr]


def test_starttls_on_587_and_login() -> None:
    s = _settings(smtp_port=587, smtp_user="u", smtp_password="p", smtp_host="smtp.example.org")
    mail.send_email("a@b.hr", "s", "<p>x</p>", "x", settings=s)
    smtp = FakeSMTP.instances[0]
    assert smtp.started_tls
    assert smtp.login_args == ("u", "p")


def test_header_injection_is_rejected() -> None:
    with pytest.raises(ValueError, match="header injection"):
        mail.send_email("a@b.hr\r\nBcc: x@y.z", "s", "h", "t", settings=_settings())
    with pytest.raises(ValueError, match="header injection"):
        mail.send_email("a@b.hr", "s\nBcc: x@y.z", "h", "t", settings=_settings())
    assert FakeSMTP.instances == []


def test_template_env_autoescapes_html(tmp_path: Path) -> None:
    (tmp_path / "hello.html").write_text("<p>Bok, {{ name }}!</p>", encoding="utf-8")
    (tmp_path / "hello.txt").write_text("Bok, {{ name }}!", encoding="utf-8")
    env = mail.make_template_env(tmp_path)
    assert (
        mail.render_email(env, "hello.html", name="<b>Ana</b>")
        == "<p>Bok, &lt;b&gt;Ana&lt;/b&gt;!</p>"
    )
    assert mail.render_email(env, "hello.txt", name="Ana") == "Bok, Ana!"
