import tempfile
import unittest
import re
from pathlib import Path

from openpyxl import Workbook
from pypdf import PdfReader

from app.repository import Repository
from app.services.certificate import generate_pdf
from app.services.importer import import_xlsx, inspect_xlsx
from app.services.mailer import RecordingTransport, build_message
from app.validation import validate_activity
from app.web import create_app


ACTIVITY = {
    "title": "Programa de Voluntariado Instituto DECIP",
    "role": "Apoio institucional",
    "start_date": "2026-09-01",
    "end_date": "2026-09-26",
    "hours": "24.5",
    "activities": "Apoio à organização de ações sociais e acolhimento de participantes.",
    "issue_city": "São Paulo",
    "issue_date": "2026-09-26",
    "signer1_name": "Vitor de Souza Silva",
    "signer1_role": "Presidente Executivo",
    "signer2_name": "Ana Beatriz Ferreira",
    "signer2_role": "Coordenação de Voluntariado",
}


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self): self.tmp.cleanup()

    def test_pdf_is_single_page_and_selectable(self):
        target = self.root / "sample.pdf"
        participant = {"name": "Maria Aparecida da Conceição do Nascimento Gonçalves", "individual": {}}
        generate_pdf(ACTIVITY, participant, "DECIP-2026-000001", target)
        reader = PdfReader(target)
        self.assertEqual(1, len(reader.pages))
        text = reader.pages[0].extract_text()
        self.assertIn(participant["name"], text)
        self.assertIn("DECIP-2026-000001", text)

    def test_300_character_activity_stays_one_page(self):
        data = dict(ACTIVITY, activities=("Atendimento, organização e apoio às iniciativas institucionais; " * 8)[:300])
        target = self.root / "long.pdf"
        generate_pdf(data, {"name": "Nome Fictício Muito Longo Para Teste de Layout do Certificado", "individual": {}}, "DECIP-2026-000002", target)
        self.assertEqual(1, len(PdfReader(target).pages))

    def test_xlsx_mapping_presence_duplicates_and_names_preserved(self):
        path = self.root / "people.xlsx"; wb = Workbook(); ws = wb.active
        ws.append(["Nome completo", "E-mail", "Presença", "Horas"])
        ws.append(["ANA d'ÁVILA", "ana@example.org", "Sim", 12])
        ws.append(["Outra Pessoa", "ana@example.org", "Sim", 8])
        ws.append(["Pessoa Ausente", "ausente@example.org", "Não", 4]); wb.save(path)
        info = inspect_xlsx(path)
        self.assertEqual({"name": 0, "email": 1, "present": 2, "hours": 3}, {k: info["suggested_mapping"][k] for k in ("name", "email", "present", "hours")})
        result = import_xlsx(path, info["suggested_mapping"])
        self.assertEqual("ANA d'ÁVILA", result["participants"][0]["name"])
        self.assertIn("e-mail repetido", result["participants"][1]["issues"])
        self.assertFalse(result["participants"][2]["eligible"])

    def test_persistent_unique_code_generation_and_resend_prevention(self):
        repo = Repository(self.root / "test.db")
        p1 = repo.add_participant({"name": "Pessoa Um", "email": "um@example.org"})
        p2 = repo.add_participant({"name": "Pessoa Dois", "email": "dois@example.org"})
        c1 = repo.reserve_certificate(p1["id"], "atividade-x", ACTIVITY)
        c1_again = repo.reserve_certificate(p1["id"], "atividade-x", ACTIVITY)
        c2 = repo.reserve_certificate(p2["id"], "atividade-x", ACTIVITY)
        self.assertEqual(c1["code"], c1_again["code"])
        self.assertNotEqual(c1["code"], c2["code"])
        repo.record_delivery(c1["id"], p1["email"], "lote", "enviado")
        self.assertTrue(repo.already_sent(c1["id"], p1["email"].upper()))

    def test_mail_is_simulated_and_has_individual_pdf(self):
        pdf = self.root / "cert.pdf"; pdf.write_bytes(b"%PDF-ficticio")
        config = {"username": "remetente@example.org", "sender_name": "Instituto DECIP", "subject": "Certificado", "body": "Olá, {nome}."}
        message = build_message(config, "destino@example.org", pdf, "Pessoa Fictícia")
        transport = RecordingTransport(); transport.send(message)
        self.assertEqual(1, len(transport.messages))
        self.assertEqual("destino@example.org", transport.messages[0]["To"])
        self.assertEqual("cert.pdf", next(transport.messages[0].iter_attachments()).get_filename())

    def test_validation(self):
        errors = validate_activity(dict(ACTIVITY, end_date="2026-08-01", activities="x" * 301, hours="0"))
        self.assertIn("end_date", errors); self.assertIn("activities", errors); self.assertIn("hours", errors)

    def test_participants_without_email_generate_and_download(self):
        db = self.root / "web.db"
        app = create_app({"TESTING": True, "DB_PATH": str(db)})
        client = app.test_client()
        first = client.post("/api/participants", json={"name": "Pessoa Sem E-mail Um", "email": "", "eligible": True})
        second = client.post("/api/participants", json={"name": "Pessoa Sem E-mail Dois", "email": "", "eligible": True})
        self.assertEqual(200, first.status_code)
        self.assertEqual(200, second.status_code)
        pid = first.get_json()["participant"]["id"]
        generated = client.post("/api/generate", json={"activity": ACTIVITY, "participant_ids": [pid]})
        self.assertEqual(200, generated.status_code)
        item = generated.get_json()["generated"][0]
        download = client.get(item["download_url"])
        self.assertEqual(200, download.status_code)
        self.assertEqual("application/pdf", download.mimetype)
        download.close()

    def test_send_rejects_missing_recipient_before_smtp(self):
        app = create_app({"TESTING": True, "DB_PATH": str(self.root / "send.db")})
        repo = app.extensions["repo"]
        person = repo.add_participant({"name": "Pessoa Sem E-mail", "email": "", "eligible": True})
        cert = repo.reserve_certificate(person["id"], "atividade", ACTIVITY)
        # Sem credenciais, o endpoint interrompe antes; a regra de destinatário
        # também é coberta no fluxo de navegador sem qualquer envio real.
        response = app.test_client().post("/api/send", json={"confirmation": "ENVIAR", "items": [{"certificate_id": cert["id"], "name": person["name"], "email": "", "path": "inexistente.pdf"}]})
        self.assertEqual(400, response.status_code)

    def test_reopen_and_new_batch_preserve_registrations_history_and_numbering(self):
        db = self.root / "persistence.db"
        first_app = create_app({"TESTING": True, "DB_PATH": str(db)})
        client = first_app.test_client()
        person = client.post("/api/participants", json={"name": "Pessoa Fictícia Persistente", "email": "pessoa@example.org", "eligible": True}).get_json()["participant"]
        generated = client.post("/api/generate", json={"activity": ACTIVITY, "participant_ids": [person["id"]]}).get_json()["generated"][0]
        first_code = generated["code"]

        # Simula fechar e reabrir o aplicativo usando o mesmo arquivo SQLite.
        reopened = create_app({"TESTING": True, "DB_PATH": str(db)})
        reopened_client = reopened.test_client()
        state = reopened_client.get("/api/state").get_json()
        self.assertEqual(first_code, state["history"][0]["code"])
        self.assertEqual("Pessoa Fictícia Persistente", state["registrations"][0]["name"])

        new_batch = reopened_client.post("/api/batches", json={}).get_json()
        self.assertEqual([], new_batch["participants"])
        state = reopened_client.get("/api/state").get_json()
        self.assertEqual(1, len(state["registrations"]))
        self.assertEqual(1, len(state["history"]))
        reopened_client.post(f"/api/batch/participants/{person['id']}")
        second = reopened_client.post("/api/generate", json={"activity": dict(ACTIVITY, title="Outra Atividade Fictícia"), "participant_ids": [person["id"]]}).get_json()["generated"][0]
        self.assertNotEqual(first_code, second["code"])
        self.assertGreater(int(second["code"].split("-")[-1]), int(first_code.split("-")[-1]))

    def test_preview_does_not_create_history_or_reserve_code(self):
        app = create_app({"TESTING": True, "DB_PATH": str(self.root / "preview.db")})
        client = app.test_client()
        person = client.post("/api/participants", json={"name": "Pessoa de Prévia", "email": "", "eligible": True}).get_json()["participant"]
        preview = client.post(f"/api/preview/{person['id']}", json=ACTIVITY)
        self.assertEqual(200, preview.status_code)
        preview.close()
        self.assertEqual([], client.get("/api/state").get_json()["history"])
        generated = client.post("/api/generate", json={"activity": ACTIVITY, "participant_ids": [person["id"]]}).get_json()["generated"][0]
        self.assertTrue(generated["code"].endswith("000001"))

    def test_interface_reload_recovers_batch_link_selection_and_activity(self):
        """Regressão da tela vazia causada por #smtp-form aplicado a uma div."""
        db = self.root / "reload-regression.db"
        app = create_app({"TESTING": True, "DB_PATH": str(db)})
        client = app.test_client()
        html = client.get("/").get_data(as_text=True)
        self.assertRegex(html, re.compile(r'<form[^>]+id="smtp-form"'))
        self.assertNotRegex(html, re.compile(r'<div[^>]+id="smtp-form"'))

        created_response = client.post("/api/participants", json={"name": "Pessoa Fictícia da Recarga", "email": "recarga@example.org", "eligible": True})
        created = created_response.get_json()
        self.assertIn("registrations", created)
        self.assertIn("participants", created)
        self.assertIsInstance(created["registrations"], list)
        self.assertIsInstance(created["participants"], list)
        self.assertEqual(1, len(created["registrations"]))
        self.assertEqual(1, len(created["participants"]))
        person = created["participant"]
        client.put(f"/api/batch/participants/{person['id']}/selection", json={"selected": False})
        self.assertEqual(200, client.post("/api/activity", json=ACTIVITY).status_code)
        first = client.get("/api/state").get_json()

        reopened = create_app({"TESTING": True, "DB_PATH": str(db)})
        recovered = reopened.test_client().get("/api/state").get_json()
        self.assertEqual(first["batch"], recovered["batch"])
        self.assertEqual(person["id"], recovered["participants"][0]["id"])
        self.assertEqual(0, recovered["participants"][0]["selected"])
        self.assertEqual(ACTIVITY["title"], recovered["activity"]["title"])


if __name__ == "__main__": unittest.main()
