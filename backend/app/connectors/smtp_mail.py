"""连接器：SMTP 邮件通知（评审触达，动作仍在平台内完成）。"""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

from app.config import settings
from app.connectors.base import Connector


class SmtpMailConnector(Connector):
    kind = "smtp"

    def validate_config(self, cfg: dict) -> list[str]:
        errs = []
        if not (cfg.get("host") or settings().SMTP_HOST):
            errs.append("缺少 SMTP_HOST")
        if not (cfg.get("user") or settings().SMTP_USER):
            errs.append("缺少 SMTP_USER")
        return errs

    def push(self, cfg: dict, payload: dict) -> dict:
        host = cfg.get("host") or settings().SMTP_HOST
        port = int(cfg.get("port") or settings().SMTP_PORT)
        user = cfg.get("user") or settings().SMTP_USER
        password = cfg.get("password") or settings().SMTP_PASSWORD
        use_ssl = bool(cfg.get("use_ssl", settings().SMTP_USE_SSL))

        to = payload.get("to") or cfg.get("to")
        subject = payload.get("subject", "【AI 测试工作流平台】通知")
        body = payload.get("body", "")

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = formataddr((cfg.get("from_name", "AI测试平台"), user))
        msg["To"] = to

        server = smtplib.SMTP_SSL(host, port) if use_ssl else smtplib.SMTP(host, port)
        with server:
            if not use_ssl:
                server.starttls()
            server.login(user, password)
            server.sendmail(user, [to], msg.as_string())
        return {"sent": True, "to": to, "subject": subject}
