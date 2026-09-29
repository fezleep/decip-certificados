"""Servidor local de demonstração com SQLite e PDFs descartáveis/fictícios."""

from __future__ import annotations

import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.web as web
from app.repository import Repository
from app.web import create_app


DEMO_DIR = Path(tempfile.mkdtemp(prefix="decip-certificados-demo-"))
web.OUTPUT_DIR = DEMO_DIR / "output"
web.UPLOAD_DIR = DEMO_DIR / "uploads"

repository = Repository(DEMO_DIR / "demo.sqlite")
repository.save_batch_activity(
    {
        "title": "Oficina de Acolhimento Comunitário",
        "role": "Participante voluntária",
        "start_date": "2026-08-10",
        "end_date": "2026-08-12",
        "hours": "12",
        "activities": "Acolhimento de famílias, organização de materiais e apoio às atividades comunitárias.",
        "issue_city": "São Paulo",
        "issue_date": "2026-08-15",
        "signer1_name": "Marina Costa",
        "signer1_role": "Coordenação de Projetos",
        "signer2_name": "Rafael Lima",
        "signer2_role": "Direção Institucional",
    }
)

for name, email in (
    ("Ana Beatriz Almeida", "ana.demo@example.org"),
    ("Caio Henrique Martins", "caio.demo@example.org"),
    ("Luiza Fernanda Ribeiro", "luiza.demo@example.org"),
):
    repository.add_participant_to_current_batch(
        {"name": name, "email": email, "eligible": True, "present": True, "individual": {}}
    )

app = create_app({"TESTING": True, "DB_PATH": str(DEMO_DIR / "demo.sqlite")})

if __name__ == "__main__":
    print(f"Demonstração temporária: {DEMO_DIR}", flush=True)
    app.run(host="127.0.0.1", port=8768, debug=False, threaded=True)
