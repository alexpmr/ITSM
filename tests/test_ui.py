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
    assert window.tabs.count() == 9
    editor = RecordEditor(window, path, "incident")
    editor.inputs["title"].setText("Teste do desktop")
    item_id = db.create_record(path, "incident", editor.values(), "teste-ui")
    assert db.get_record(path, item_id)["title"] == "Teste do desktop"
    window.refresh_all()
    assert window.pages[1].table.rowCount() == 1
    editor.close()
    window.close()
    assert app is not None


def test_cmdb_transversal_in_ui(tmp_path):
    from itsm import cmdb
    from itsm.cmdb_ui import CIChooser
    app = QApplication.instance() or QApplication([])
    path = db.init_db(tmp_path / "with_cmdb.db")
    ci_id = cmdb.create_ci(path, {
        "code": "SERV-DB", "name": "Banco",
        "ci_type": "database", "criticality": "critical",
    })
    window = MainWindow(path)
    assert window.tabs.tabText(7) == "CMDB"
    editor = RecordEditor(window, path, "change")
    chooser = CIChooser(editor, path, kind="change")
    assert chooser.table.rowCount() == 1
    chooser.controls[0][1].setChecked(True)
    assert chooser.values() == [(ci_id, "target")]
    editor.selected_cis = chooser.values()
    record_id = db.create_record(path, "change", {
        **editor.values(), "title": "Mudança banco"
    })
    assert cmdb.list_record_cis(path, record_id)[0]["code"] == "SERV-DB"
    window.refresh_all()
    assert window.pages[7].table.rowCount() == 1
    chooser.close()
    editor.close()
    window.close()
    assert app is not None
