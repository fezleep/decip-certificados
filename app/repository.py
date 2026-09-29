from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .config import DB_PATH, ensure_dirs


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS participants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL COLLATE NOCASE,
  eligible INTEGER NOT NULL DEFAULT 1,
  present INTEGER,
  individual_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS certificates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT UNIQUE,
  participant_id INTEGER NOT NULL REFERENCES participants(id),
  activity_key TEXT NOT NULL,
  data_json TEXT NOT NULL,
  pdf_path TEXT,
  generated_at TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(participant_id, activity_key)
);
CREATE TABLE IF NOT EXISTS generation_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  certificate_id INTEGER NOT NULL REFERENCES certificates(id),
  pdf_path TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS delivery_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  certificate_id INTEGER NOT NULL REFERENCES certificates(id),
  recipient TEXT NOT NULL,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_key TEXT NOT NULL UNIQUE,
  activity_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS batch_participants (
  batch_id INTEGER NOT NULL REFERENCES batches(id),
  participant_id INTEGER NOT NULL REFERENCES participants(id),
  selected INTEGER NOT NULL DEFAULT 1,
  added_at TEXT NOT NULL,
  PRIMARY KEY(batch_id, participant_id)
);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Repository:
    def __init__(self, path: str | Path = DB_PATH):
        ensure_dirs()
        self.path = Path(path)
        self.init()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=20)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def init(self):
        with self.connect() as con:
            con.executescript(SCHEMA)
            con.execute("DROP INDEX IF EXISTS uq_participant_email")

            columns = {r["name"] for r in con.execute("PRAGMA table_info(participants)")}
            if "archived_at" not in columns:
                con.execute("ALTER TABLE participants ADD COLUMN archived_at TEXT")
            link_columns = {r["name"] for r in con.execute("PRAGMA table_info(batch_participants)")}
            if "selected" not in link_columns:
                con.execute("ALTER TABLE batch_participants ADD COLUMN selected INTEGER NOT NULL DEFAULT 1")
            if not con.execute("SELECT 1 FROM batches LIMIT 1").fetchone():
                old_activity = con.execute("SELECT value FROM settings WHERE key='activity'").fetchone()
                activity = old_activity["value"] if old_activity else "{}"
                stamp = now()
                cur = con.execute(
                    "INSERT INTO batches(batch_key,activity_json,created_at,updated_at) VALUES(?,?,?,?)",
                    (f"lote-inicial-{stamp}", activity, stamp, stamp),
                )
                batch_id = cur.lastrowid
                con.execute(
                    "INSERT OR IGNORE INTO batch_participants(batch_id,participant_id,added_at) "
                    "SELECT ?,id,? FROM participants WHERE eligible=1 AND archived_at IS NULL",
                    (batch_id, stamp),
                )
                con.execute(
                    "INSERT INTO settings(key,value,updated_at) VALUES('current_batch_id',?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                    (json.dumps(batch_id), stamp),
                )
            else:
                current = con.execute("SELECT value FROM settings WHERE key='current_batch_id'").fetchone()
                valid = None
                if current:
                    try:
                        valid = con.execute("SELECT id FROM batches WHERE id=?", (json.loads(current["value"]),)).fetchone()
                    except (TypeError, ValueError, json.JSONDecodeError):
                        valid = None
                if not valid:
                    latest = con.execute("SELECT id FROM batches ORDER BY id DESC LIMIT 1").fetchone()
                    con.execute(
                        "INSERT INTO settings(key,value,updated_at) VALUES('current_batch_id',?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                        (json.dumps(latest["id"]), now()),
                    )

    def list_participants(self, include_archived: bool = False) -> list[dict]:
        with self.connect() as con:
            where = "" if include_archived else "WHERE archived_at IS NULL"
            rows = con.execute(f"SELECT * FROM participants {where} ORDER BY name COLLATE NOCASE").fetchall()
        return [dict(r) | {"individual": json.loads(r["individual_json"])} for r in rows]

    def add_participant(self, data: dict) -> dict:
        stamp = now()
        with self.connect() as con:
            cur = con.execute(
                "INSERT INTO participants(name,email,eligible,present,individual_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (data["name"].strip(), data["email"].strip(), int(data.get("eligible", True)), data.get("present"), json.dumps(data.get("individual", {}), ensure_ascii=False), stamp, stamp),
            )
            pid = cur.lastrowid
        return self.get_participant(pid)

    def add_participant_to_current_batch(self, data: dict) -> dict:
        """Grava cadastro e vínculo do lote na mesma transação."""
        stamp = now()
        with self.connect() as con:
            setting = con.execute("SELECT value FROM settings WHERE key='current_batch_id'").fetchone()
            if not setting:
                raise RuntimeError("Não foi possível identificar o lote ativo.")
            batch_id = json.loads(setting["value"])
            if not con.execute("SELECT 1 FROM batches WHERE id=?", (batch_id,)).fetchone():
                raise RuntimeError("O lote ativo não existe mais.")
            cur = con.execute(
                "INSERT INTO participants(name,email,eligible,present,individual_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (data["name"].strip(), data["email"].strip(), int(data.get("eligible", True)), data.get("present"), json.dumps(data.get("individual", {}), ensure_ascii=False), stamp, stamp),
            )
            pid = cur.lastrowid
            con.execute(
                "INSERT INTO batch_participants(batch_id,participant_id,selected,added_at) VALUES(?,?,?,?)",
                (batch_id, pid, int(data.get("eligible", True)), stamp),
            )
        return self.get_participant(pid)

    def update_participant(self, pid: int, data: dict) -> dict:
        current = self.get_participant(pid)
        individual = data.get("individual", current["individual"])
        with self.connect() as con:
            con.execute(
                "UPDATE participants SET name=?,email=?,eligible=?,present=?,individual_json=?,updated_at=? WHERE id=?",
                (data.get("name", current["name"]).strip(), data.get("email", current["email"]).strip(), int(data.get("eligible", current["eligible"])), data.get("present", current["present"]), json.dumps(individual, ensure_ascii=False), now(), pid),
            )
        return self.get_participant(pid)

    def get_participant(self, pid: int) -> dict:
        with self.connect() as con:
            row = con.execute("SELECT * FROM participants WHERE id=?", (pid,)).fetchone()
        if not row:
            raise KeyError("Participante não encontrado.")
        return dict(row) | {"individual": json.loads(row["individual_json"])}

    def archive_participant(self, pid: int) -> dict:
        self.get_participant(pid)
        with self.connect() as con:
            con.execute("UPDATE participants SET archived_at=?,updated_at=? WHERE id=?", (now(), now(), pid))
            con.execute("DELETE FROM batch_participants WHERE participant_id=?", (pid,))
        return self.get_participant(pid)

    def participant_certificate_count(self, pid: int) -> int:
        with self.connect() as con:
            return con.execute("SELECT COUNT(*) FROM certificates WHERE participant_id=?", (pid,)).fetchone()[0]

    def current_batch(self) -> dict:
        batch_id = self.get_setting("current_batch_id")
        with self.connect() as con:
            row = con.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
        if not row:
            raise RuntimeError("Lote atual não encontrado.")
        return dict(row) | {"activity": json.loads(row["activity_json"])}

    def new_batch(self) -> dict:
        stamp = now()
        with self.connect() as con:
            cur = con.execute(
                "INSERT INTO batches(batch_key,activity_json,created_at,updated_at) VALUES(?,?,?,?)",
                (f"lote-{stamp}-{datetime.now().microsecond}", "{}", stamp, stamp),
            )
            batch_id = cur.lastrowid
        self.save_setting("current_batch_id", batch_id)
        return self.current_batch()

    def save_batch_activity(self, data: dict):
        batch = self.current_batch()
        with self.connect() as con:
            con.execute("UPDATE batches SET activity_json=?,updated_at=? WHERE id=?", (json.dumps(data, ensure_ascii=False), now(), batch["id"]))

    def list_batch_participants(self) -> list[dict]:
        batch = self.current_batch()
        with self.connect() as con:
            rows = con.execute(
                "SELECT p.*,bp.selected FROM participants p JOIN batch_participants bp ON bp.participant_id=p.id "
                "WHERE bp.batch_id=? AND p.archived_at IS NULL ORDER BY p.name COLLATE NOCASE",
                (batch["id"],),
            ).fetchall()
        return [dict(r) | {"individual": json.loads(r["individual_json"])} for r in rows]

    def add_to_current_batch(self, pid: int):
        participant = self.get_participant(pid)
        if participant.get("archived_at"):
            raise ValueError("Cadastro arquivado não pode ser adicionado ao lote.")
        batch = self.current_batch()
        with self.connect() as con:
            con.execute("INSERT OR IGNORE INTO batch_participants(batch_id,participant_id,selected,added_at) VALUES(?,?,?,?)", (batch["id"], pid, int(participant["eligible"]), now()))

    def set_current_batch_selection(self, pid: int, selected: bool):
        batch = self.current_batch()
        with self.connect() as con:
            cur = con.execute("UPDATE batch_participants SET selected=? WHERE batch_id=? AND participant_id=?", (int(selected), batch["id"], pid))
            if not cur.rowcount:
                raise KeyError("Participante não está no lote atual.")

    def remove_from_current_batch(self, pid: int):
        batch = self.current_batch()
        with self.connect() as con:
            con.execute("DELETE FROM batch_participants WHERE batch_id=? AND participant_id=?", (batch["id"], pid))

    def save_setting(self, key: str, value):
        with self.connect() as con:
            con.execute(
                "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, json.dumps(value, ensure_ascii=False), now()),
            )

    def get_setting(self, key: str, default=None):
        with self.connect() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def reserve_certificate(self, participant_id: int, activity_key: str, data: dict) -> dict:
        with self.connect() as con:
            existing = con.execute("SELECT * FROM certificates WHERE participant_id=? AND activity_key=?", (participant_id, activity_key)).fetchone()
            if existing:
                con.execute("UPDATE certificates SET data_json=? WHERE id=?", (json.dumps(data, ensure_ascii=False), existing["id"]))
                cid = existing["id"]
            else:
                cur = con.execute(
                    "INSERT INTO certificates(participant_id,activity_key,data_json,created_at) VALUES(?,?,?,?)",
                    (participant_id, activity_key, json.dumps(data, ensure_ascii=False), now()),
                )
                cid = cur.lastrowid
                code = f"DECIP-{datetime.now().year}-{cid:06d}"
                con.execute("UPDATE certificates SET code=? WHERE id=?", (code, cid))
            row = con.execute("SELECT * FROM certificates WHERE id=?", (cid,)).fetchone()
        return dict(row) | {"data": json.loads(row["data_json"])}

    def mark_generated(self, certificate_id: int, pdf_path: str):
        stamp = now()
        with self.connect() as con:
            con.execute("UPDATE certificates SET pdf_path=?,generated_at=? WHERE id=?", (pdf_path, stamp, certificate_id))
            con.execute("INSERT INTO generation_events(certificate_id,pdf_path,created_at) VALUES(?,?,?)", (certificate_id, pdf_path, stamp))

    def record_delivery(self, certificate_id: int, recipient: str, kind: str, status: str, detail: str = ""):
        with self.connect() as con:
            con.execute("INSERT INTO delivery_events(certificate_id,recipient,kind,status,detail,created_at) VALUES(?,?,?,?,?,?)", (certificate_id, recipient, kind, status, detail, now()))

    def already_sent(self, certificate_id: int, recipient: str) -> bool:
        with self.connect() as con:
            row = con.execute("SELECT 1 FROM delivery_events WHERE certificate_id=? AND recipient=? COLLATE NOCASE AND kind='lote' AND status='enviado' LIMIT 1", (certificate_id, recipient)).fetchone()
        return bool(row)

    def history(self) -> list[dict]:
        with self.connect() as con:
            rows = con.execute("""
                SELECT c.id,c.code,p.name,p.email,c.activity_key,c.pdf_path,c.generated_at,
                  json_extract(c.data_json, '$.title') AS activity_title,
                  (SELECT status FROM delivery_events d WHERE d.certificate_id=c.id AND d.kind='lote' ORDER BY d.id DESC LIMIT 1) AS last_delivery,
                  (SELECT created_at FROM delivery_events d WHERE d.certificate_id=c.id AND d.kind='lote' AND d.status='enviado' ORDER BY d.id DESC LIMIT 1) AS delivered_at
                FROM certificates c JOIN participants p ON p.id=c.participant_id ORDER BY c.id DESC
            """).fetchall()
        return [dict(r) for r in rows]

    def get_certificate(self, certificate_id: int) -> dict:
        with self.connect() as con:
            row = con.execute(
                "SELECT c.*,p.name,p.email FROM certificates c JOIN participants p ON p.id=c.participant_id WHERE c.id=?",
                (certificate_id,),
            ).fetchone()
        if not row:
            raise KeyError("Certificado não encontrado.")
        return dict(row)
