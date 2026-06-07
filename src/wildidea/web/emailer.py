"""SMTP email helpers."""
from __future__ import annotations

import smtplib
from html import escape
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from .config import settings


class EmailNotConfigured(RuntimeError):
    """Raised when SMTP settings are incomplete."""


def _build_verification_message(email: str, code: str, sender: str) -> EmailMessage:
    ttl = settings.email_code_ttl_minutes
    message = EmailMessage()
    message["Subject"] = "WildIdea 注册验证码"
    message["From"] = formataddr((settings.smtp_from_name, sender))
    message["To"] = email
    message["Date"] = formatdate(localtime=True)
    if "@" in sender:
        message["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[1])
    else:
        message["Message-ID"] = make_msgid()
    message.set_content(
        "\n".join([
            f"你的 WildIdea 注册验证码是：{code}",
            "",
            f"验证码 {ttl} 分钟内有效。",
            "如果不是你本人操作，可以忽略这封邮件。",
        ])
    )

    safe_code = escape(code)
    safe_ttl = escape(str(ttl))
    message.add_alternative(
        f"""\
<!doctype html>
<html lang="zh-CN">
  <body style="margin:0;background:#f4f0df;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',Arial,sans-serif;color:#1f2528;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f0df;padding:32px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#fffdf2;border:3px solid #232629;border-radius:10px;box-shadow:6px 6px 0 #232629;overflow:hidden;">
            <tr>
              <td style="padding:22px 28px 16px;border-bottom:3px solid #232629;background:#fff7c4;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  <tr>
                    <td style="font-size:22px;font-weight:800;letter-spacing:0;color:#171a1c;">WildIdea</td>
                    <td align="right" style="font-size:13px;font-weight:700;color:#5570ac;">邮箱验证</td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:34px 28px 30px;">
                <div style="font-size:16px;line-height:1.8;color:#3a4248;">你好，</div>
                <div style="margin-top:6px;font-size:16px;line-height:1.8;color:#3a4248;">这是你的 WildIdea 注册验证码：</div>
                <div style="margin:24px 0 18px;padding:22px 16px;background:#eaf2f6;border:3px solid #232629;border-radius:8px;text-align:center;">
                  <div style="font-size:38px;line-height:1.1;font-weight:900;letter-spacing:8px;color:#111719;font-family:Menlo,Consolas,'Courier New',monospace;">{safe_code}</div>
                </div>
                <div style="display:inline-block;padding:8px 12px;background:#ffe28a;border:2px solid #232629;border-radius:6px;font-size:14px;font-weight:800;color:#1d2225;">{safe_ttl} 分钟内有效</div>
                <div style="margin-top:22px;font-size:14px;line-height:1.8;color:#66727a;">如果不是你本人操作，可以忽略这封邮件。为了账号安全，请不要把验证码转发给其他人。</div>
              </td>
            </tr>
          </table>
          <div style="max-width:560px;margin-top:18px;font-size:12px;line-height:1.7;color:#89929a;text-align:center;">WildIdea 帮你想出不一样的点子</div>
        </td>
      </tr>
    </table>
  </body>
</html>
""",
        subtype="html",
    )
    return message


def send_verification_email(email: str, code: str) -> None:
    """Send a registration verification code."""
    if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password:
        raise EmailNotConfigured("邮件服务未配置，请设置 SMTP 环境变量")
    sender = settings.smtp_from_email or settings.smtp_username
    message = _build_verification_message(email, code, sender)

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
