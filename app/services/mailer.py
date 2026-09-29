from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path


def build_message(config: dict, recipient: str, pdf: Path, participant_name: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = config.get("subject") or "Seu certificado de voluntariado — Instituto DECIP"
    msg["From"] = formataddr((config.get("sender_name", "Instituto DECIP"), config["username"]))
    msg["To"] = recipient
    if config.get("reply_to"): msg["Reply-To"] = config["reply_to"]
    body = (config.get("body") or "Olá, {nome}.\n\nSegue seu certificado de voluntariado.\n\nInstituto DECIP").replace("{nome}", participant_name)
    msg.set_content(body)
    msg.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=pdf.name)
    return msg


class SMTPTransport:
    def __init__(self, config: dict, password: str): self.config, self.password = config, password
    def send(self, message: EmailMessage):
        host, port = self.config["host"], int(self.config.get("port", 587))
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo(); smtp.starttls(context=ssl.create_default_context()); smtp.ehlo()
            smtp.login(self.config["username"], self.password)
            smtp.send_message(message)


class RecordingTransport:
    """Transporte de teste: registra mensagens em memória, sem rede."""
    def __init__(self, fail_for=None): self.messages, self.fail_for = [], set(fail_for or [])
    def send(self, message: EmailMessage):
        if message["To"] in self.fail_for: raise RuntimeError("Falha SMTP simulada")
        self.messages.append(message)

