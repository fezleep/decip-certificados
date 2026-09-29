from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "decip.db"
KEYRING_SERVICE = "Instituto DECIP - Certificados"


def ensure_dirs() -> None:
    for directory in (DATA_DIR, OUTPUT_DIR, UPLOAD_DIR):
        directory.mkdir(parents=True, exist_ok=True)

