from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def valid_email(value: str) -> bool:
    return bool(EMAIL_RE.fullmatch(clean(value)))


def parse_date(value: str, label: str, errors: dict) -> date | None:
    try:
        return date.fromisoformat(clean(value))
    except ValueError:
        errors[label] = "Informe uma data válida."
        return None


def parse_hours(value, errors: dict, label: str = "horas") -> Decimal | None:
    try:
        number = Decimal(str(value).replace(",", "."))
        if number <= 0 or number > 10000:
            raise InvalidOperation
        return number
    except (InvalidOperation, ValueError):
        errors[label] = "Informe uma carga horária maior que zero."
        return None


def validate_activity(data: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    required = {
        "title": "Informe o nome da atividade.",
        "role": "Informe a função exercida.",
        "start_date": "Informe a data inicial.",
        "end_date": "Informe a data final.",
        "hours": "Informe a carga horária.",
        "activities": "Descreva as atividades desenvolvidas.",
        "issue_city": "Informe a cidade de emissão.",
        "issue_date": "Informe a data de emissão.",
        "signer1_name": "Informe o nome do primeiro responsável.",
        "signer1_role": "Informe o cargo do primeiro responsável.",
    }
    for field, message in required.items():
        if not clean(data.get(field)):
            errors[field] = message
    start = parse_date(data.get("start_date", ""), "start_date", errors) if data.get("start_date") else None
    end = parse_date(data.get("end_date", ""), "end_date", errors) if data.get("end_date") else None
    if start and end and end < start:
        errors["end_date"] = "A data final não pode ser anterior à inicial."
    if data.get("issue_date"):
        parse_date(data["issue_date"], "issue_date", errors)
    if data.get("hours") not in (None, ""):
        parse_hours(data["hours"], errors, "hours")
    if len(clean(data.get("activities"))) > 300:
        errors["activities"] = "Use no máximo 300 caracteres."
    return errors


def validate_participant(data: dict, allow_invalid_email: bool = True) -> dict[str, str]:
    errors = {}
    if not clean(data.get("name")):
        errors["name"] = "Informe o nome completo."
    email = clean(data.get("email"))
    if email and not valid_email(email) and not allow_invalid_email:
        errors["email"] = "Informe um e-mail válido, como nome@exemplo.org."
    return errors
