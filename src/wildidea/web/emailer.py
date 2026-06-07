"""SMTP email helpers."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from .config import settings


class EmailNotConfigured(RuntimeError):
    """Raised when SMTP settings are incomplete."""


def send_verification_email(email: str, code: str) -> None:
    """Send a registration verification code."""
    if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password:
        raise EmailNotConfigured("邮件服务未配置，请设置 SMTP 环境变量")
    sender = settings.smtp_from_email or settings.smtp_username
    message = EmailMessage()
    message["Subject"] = "WildIdea 注册验证码"
    message["From"] = formataddr((settings.smtp_from_name, sender))
    message["To"] = email
    message.set_content(
        "\n".join([
            f"你的 WildIdea 注册验证码是：{code}",
            "",
            f"验证码 {settings.email_code_ttl_minutes} 分钟内有效。",
            "如果不是你本人操作，可以忽略这封邮件。",
        ])
    )

    if settings.smtp_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
