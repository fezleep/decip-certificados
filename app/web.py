from __future__ import annotations

import hashlib
import json
from pathlib import Path

import keyring
from flask import Flask, jsonify, render_template, request, send_file

from .config import BASE_DIR, KEYRING_SERVICE, OUTPUT_DIR, UPLOAD_DIR, ensure_dirs
from .repository import Repository
from .services.certificate import generate_pdf, safe_filename
from .services.importer import import_xlsx, inspect_xlsx
from .services.mailer import SMTPTransport, build_message
from .validation import clean, valid_email, validate_activity, validate_participant
from .launcher import SERVICE_ID


def create_app(test_config=None):
    ensure_dirs()
    app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
    app.config.update(MAX_CONTENT_LENGTH=12 * 1024 * 1024)
    if test_config: app.config.update(test_config)
    repo = Repository(app.config.get("DB_PATH") or BASE_DIR / "data" / "decip.db")
    app.extensions["repo"] = repo

    def body(): return request.get_json(silent=True) or {}
    def error(message, status=400, fields=None): return jsonify({"ok": False, "message": message, "fields": fields or {}}), status
    def participant_state(item=None):
        batch = repo.current_batch()
        result = {
            "registrations": repo.list_participants(),
            "participants": repo.list_batch_participants(),
            "batch": {"id": batch["id"], "key": batch["batch_key"]},
        }
        if item is not None: result["participant"] = item
        return result

    @app.get("/")
    def index(): return render_template("index.html")

    @app.get("/api/health")
    def health(): return jsonify({"service": SERVICE_ID, "status": "ok"})

    @app.get("/api/state")
    def state():
        batch = repo.current_batch()
        return jsonify({"registrations": repo.list_participants(), "participants": repo.list_batch_participants(),
                        "batch": {"id": batch["id"], "key": batch["batch_key"]},
                        "activity": batch["activity"], "smtp": repo.get_setting("smtp", {}), "history": repo.history()})

    @app.post("/api/batches")
    def new_batch():
        batch = repo.new_batch()
        return jsonify({"ok": True, "batch": {"id": batch["id"], "key": batch["batch_key"]}, "activity": {}, "participants": []})

    @app.post("/api/batch/participants/<int:pid>")
    def add_batch_participant(pid):
        try: repo.add_to_current_batch(pid)
        except (KeyError, ValueError) as exc: return error(str(exc), 404)
        return jsonify({"ok": True, "participants": repo.list_batch_participants()})

    @app.put("/api/batch/participants/<int:pid>/selection")
    def select_batch_participant(pid):
        try: repo.set_current_batch_selection(pid, bool(body().get("selected")))
        except KeyError as exc: return error(str(exc), 404)
        return jsonify({"ok": True, "participants": repo.list_batch_participants()})

    @app.delete("/api/batch/participants/<int:pid>")
    def remove_batch_participant(pid):
        repo.remove_from_current_batch(pid)
        return jsonify({"ok": True, "participants": repo.list_batch_participants()})

    @app.post("/api/participants")
    def add_participant():
        data = body(); errors = validate_participant(data)
        if errors: return error("Revise os campos destacados.", fields=errors)
        item = repo.add_participant_to_current_batch(data)
        return jsonify({"ok": True, **participant_state(item),
                        "email_warning": bool(clean(data.get("email"))) and not valid_email(data.get("email", ""))})

    @app.put("/api/participants/<int:pid>")
    def update_participant(pid):
        data = body(); errors = validate_participant(data)
        if errors: return error("Revise os campos destacados.", fields=errors)
        item = repo.update_participant(pid, data)
        return jsonify({"ok": True, **participant_state(item),
                        "email_warning": bool(clean(data.get("email"))) and not valid_email(data.get("email", ""))})

    @app.delete("/api/participants/<int:pid>")
    def archive_participant(pid):
        try:
            count = repo.participant_certificate_count(pid)
            item = repo.archive_participant(pid)
        except KeyError as exc: return error(str(exc), 404)
        return jsonify({"ok": True, "archived": True, "certificate_count": count, "participant": item,
                        "message": "Cadastro arquivado. Certificados, PDFs e histórico foram preservados."})

    @app.post("/api/import/inspect")
    def inspect_import():
        file = request.files.get("file")
        if not file or not file.filename.lower().endswith(".xlsx"): return error("Escolha um arquivo XLSX válido.")
        token = hashlib.sha256(file.read()).hexdigest()[:16]; file.seek(0)
        path = UPLOAD_DIR / f"{token}.xlsx"; file.save(path)
        try: info = inspect_xlsx(path)
        except Exception: return error("Não foi possível ler a planilha. Verifique se o arquivo XLSX não está corrompido.")
        return jsonify({"ok": True, "token": token, **info})

    @app.post("/api/import/commit")
    def commit_import():
        data = body(); path = UPLOAD_DIR / f"{data.get('token','')}.xlsx"
        if not path.exists(): return error("A planilha temporária não foi encontrada. Selecione-a novamente.")
        mapping = data.get("mapping", {})
        if "name" not in mapping: return error("Mapeie pelo menos a coluna Nome completo.")
        result = import_xlsx(path, mapping); saved, duplicates = 0, 0
        for participant in result["participants"]:
            item = repo.add_participant(participant); repo.add_to_current_batch(item["id"]); saved += 1
        return jsonify({"ok": True, "saved": saved, "duplicates": duplicates, "issues": result["issues"],
                        "registrations": repo.list_participants(), "participants": repo.list_batch_participants()})

    @app.post("/api/activity")
    def save_activity():
        data = body(); errors = validate_activity(data)
        if errors: return error("Revise os dados da atividade.", fields=errors)
        repo.save_batch_activity(data)
        return jsonify({"ok": True})

    def certificate_for(pid: int, data: dict, preview=False):
        participant = repo.get_participant(pid)
        errors = validate_activity(data)
        if errors: raise ValueError(json.dumps(errors, ensure_ascii=False))
        activity_key = repo.current_batch()["batch_key"]
        cert = repo.reserve_certificate(pid, activity_key, data)
        folder = OUTPUT_DIR / safe_filename(data["title"])
        suffix = "-PREVIA" if preview else ""
        path = folder / f"{cert['code']}-{safe_filename(participant['name'])}{suffix}.pdf"
        generate_pdf(data, participant, cert["code"], path)
        if not preview: repo.mark_generated(cert["id"], str(path))
        return cert, participant, path

    @app.post("/api/preview/<int:pid>")
    def preview(pid):
        data = body(); errors = validate_activity(data)
        if errors: return error("Revise os dados antes da prévia.", fields=errors)
        participant = repo.get_participant(pid)
        folder = OUTPUT_DIR / safe_filename(data["title"])
        path = folder / f"PREVIA-{safe_filename(participant['name'])}.pdf"
        generate_pdf(data, participant, "PRÉVIA — código reservado somente ao gerar", path)
        return send_file(path, mimetype="application/pdf", as_attachment=False, download_name=path.name)

    @app.post("/api/generate")
    def generate_batch():
        data = body(); activity = data.get("activity", {}); ids = data.get("participant_ids", [])
        errors = validate_activity(activity)
        if errors: return error("Revise os dados antes de gerar.", fields=errors)
        if not ids: return error("Selecione pelo menos um participante elegível.")
        generated, failures = [], []
        for pid in ids:
            try:
                cert, participant, path = certificate_for(int(pid), activity)
                generated.append({"id": cert["id"], "code": cert["code"], "name": participant["name"], "email": participant["email"], "path": str(path), "download_url": f"/api/certificates/{cert['id']}/download"})
            except Exception as exc: failures.append({"participant_id": pid, "reason": str(exc)})
        return jsonify({"ok": True, "generated": generated, "failures": failures, "history": repo.history()})

    @app.get("/api/certificates/<int:certificate_id>/download")
    def download_certificate(certificate_id):
        try: certificate = repo.get_certificate(certificate_id)
        except KeyError: return error("Certificado não encontrado.", 404)
        path = Path(certificate.get("pdf_path") or "")
        if not path.is_file(): return error("O PDF ainda não foi gerado.", 404)
        return send_file(path, mimetype="application/pdf", as_attachment=True, download_name=path.name)

    @app.post("/api/settings/smtp")
    def save_smtp():
        data = body(); password = data.pop("password", "")
        if password:
            if not clean(data.get("username")): return error("Informe o usuário antes de salvar a senha.")
            keyring.set_password(KEYRING_SERVICE, clean(data["username"]), password)
        repo.save_setting("smtp", data)
        return jsonify({"ok": True, "password_saved": bool(password)})

    @app.post("/api/send")
    def send_batch():
        data = body()
        if data.get("confirmation") != "ENVIAR": return error("Digite ENVIAR para confirmar o lote.")
        smtp = repo.get_setting("smtp", {})
        username = smtp.get("username", ""); password = keyring.get_password(KEYRING_SERVICE, username) if username else None
        if not username or not password: return error("Configure o SMTP e salve a senha no cofre do sistema.")
        transport = SMTPTransport(smtp, password); sent, skipped, failures = [], [], []
        for item in data.get("items", []):
            cid, recipient, pdf = int(item["certificate_id"]), item["email"], Path(item["path"])
            if not valid_email(recipient):
                failures.append({"email": recipient or "(sem e-mail)", "reason": "Destinatário sem e-mail válido."})
                continue
            if repo.already_sent(cid, recipient): skipped.append(recipient); continue
            try:
                transport.send(build_message(smtp, recipient, pdf, item["name"]))
                repo.record_delivery(cid, recipient, "teste" if data.get("test") else "lote", "enviado")
                sent.append(recipient)
            except Exception as exc:
                repo.record_delivery(cid, recipient, "teste" if data.get("test") else "lote", "falha", type(exc).__name__)
                failures.append({"email": recipient, "reason": "O servidor não aceitou esta mensagem."})
        return jsonify({"ok": True, "sent": sent, "skipped": skipped, "failures": failures})

    return app


def default_activity():
    return {
        "title": "Programa de Voluntariado Instituto DECIP", "role": "Voluntária de apoio institucional",
        "start_date": "2026-09-01", "end_date": "2026-09-26", "hours": "24",
        "activities": "Apoio à organização de ações sociais, acolhimento de participantes e suporte às iniciativas institucionais.",
        "issue_city": "São Paulo", "issue_date": "2026-09-26",
        "signer1_name": "Vitor de Souza Silva", "signer1_role": "Presidente Executivo",
        "signer2_name": "Ana Beatriz Ferreira", "signer2_role": "Coordenação de Voluntariado",
    }
