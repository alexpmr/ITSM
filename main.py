"""Inicializador da aplicação Windows PT2VHF ITSM."""
import sys
from pathlib import Path

# Facilita a execução a partir do checkout; PyInstaller resolve o pacote no build.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from itsm import db
from itsm.ui import run

if __name__ == "__main__":
    database = db.init_db(db.default_database_path())
    raise SystemExit(run(database))
