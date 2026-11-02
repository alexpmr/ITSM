"""Teste superficial da interface Qt sem abrir janelas reais no runner."""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from itsm import db
from itsm.ui import MainWindow, RecordEditor


def test_windows_interface_opens_and_lists_records(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = db.init_db(tmp_path / "ui.db")
    window = MainWindow(path)
    assert window.tabs.count() == 7
    editor = RecordEditor(window, path, "incident")
    editor.inputs["title"].setText("Teste do desktop")
    item_id = db.create_record(path, "incident", editor.values(), "teste-ui")
    assert db.get_record(path, item_id)["title"] == "Teste do desktop"
    window.refresh_all()
    assert window.pages[1].table.rowCount() == 1
    editor.close()
    window.close()
    assert app is not None
