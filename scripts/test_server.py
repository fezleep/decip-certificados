import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.web import create_app

app = create_app({"TESTING": True, "DB_PATH": "data/ui-e2e.db"})
app.run(host="127.0.0.1", port=8766, debug=False, threaded=True)
