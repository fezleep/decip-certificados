from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from openpyxl import load_workbook

from ..validation import clean, valid_email

ALIASES = {
    "name": {"nome", "nome completo", "participante", "nombre", "nome do participante"},
    "email": {"email", "e mail", "correo", "correio eletronico"},
    "present": {"presente", "presenca", "compareceu", "asistio", "assistiu"},
    "eligible": {"elegivel", "aprovado", "recebe certificado", "certificado"},
    "role": {"funcao", "funcao exercida", "cargo"},
    "hours": {"horas", "carga horaria", "total de horas"},
    "activities": {"atividades", "atividades desenvolvidas", "descricao"},
}
YES = {"sim", "s", "yes", "y", "1", "true", "presente", "aprovado"}
NO = {"nao", "n", "no", "0", "false", "ausente", "reprovado"}


def normalize(value) -> str:
    text = unicodedata.normalize("NFKD", clean(value)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def inspect_xlsx(path: str | Path) -> dict:
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        headers = [clean(v) for v in next(rows, ())]
        sample = [[clean(v) for v in row] for _, row in zip(range(5), rows)]
    finally:
        wb.close()
    mapping = {}
    normalized = [normalize(h) for h in headers]
    for field, aliases in ALIASES.items():
        for i, header in enumerate(normalized):
            if header in {normalize(a) for a in aliases}:
                mapping[field] = i
                break
    return {"headers": headers, "sample": sample, "suggested_mapping": mapping}


def import_xlsx(path: str | Path, mapping: dict) -> dict:
    wb = load_workbook(path, read_only=True, data_only=True)
    participants, issues, seen = [], [], set()
    try:
        ws = wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        next(rows, None)
        for number, row in enumerate(rows, 2):
            def value(field):
                index = mapping.get(field)
                return clean(row[int(index)]) if index not in (None, "") and int(index) < len(row) else ""
            name, email = value("name"), value("email")
            if not any((name, email)):
                continue
            row_issues = []
            if not name: row_issues.append("nome ausente")
            if email and not valid_email(email): row_issues.append("e-mail inválido; PDF liberado, envio bloqueado")
            if email and email.lower() in seen: row_issues.append("e-mail repetido")
            if email: seen.add(email.lower())
            present_raw, eligible_raw = normalize(value("present")), normalize(value("eligible"))
            present = None if "present" not in mapping else present_raw in YES
            eligible = (present is not False) and (eligible_raw not in NO) and bool(name)
            participant = {
                "name": name, "email": email, "present": present, "eligible": eligible,
                "individual": {"role": value("role"), "hours": value("hours"), "activities": value("activities")},
                "issues": row_issues, "source_row": number,
            }
            participants.append(participant)
            if row_issues: issues.append({"row": number, "problems": row_issues})
    finally:
        wb.close()
    return {"participants": participants, "issues": issues}
