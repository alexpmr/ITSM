"""Garante integridade do mapa ITIL e aderência visual à funcionalidade REAL."""
import os

from itsm.itil_catalog import (
    BY_KEY, GROUP_GENERAL, GROUP_PRODUCT, PRACTICES,
    IMPLEMENTED_MVP, MODULE_TABS, counts, implementation_status, summary,
)

def test_itil_map_has_34_unique_practices():
    assert len(PRACTICES) == 34
    assert len(BY_KEY) == 34
    assert len({p.key for p in PRACTICES}) == 34
    assert sum(p.group == GROUP_PRODUCT for p in PRACTICES) == 22
    assert sum(p.group == GROUP_GENERAL for p in PRACTICES) == 12

def test_only_delivered_modules_are_highlighted():
    assert IMPLEMENTED_MVP == {"incident", "request", "change", "problem", "itam"}
    assert set(MODULE_TABS) == IMPLEMENTED_MVP
    assert counts() == {"total": 34, "mvp": 5, "planned": 29}
    for key in IMPLEMENTED_MVP:
        assert implementation_status(key) == "mvp"
        assert summary(key)["tab_index"] is not None

def test_service_catalog_is_planned_and_visible():
    details = summary("service_catalog")
    assert details["group"] == GROUP_PRODUCT
    assert details["status"] == "planned"
    assert details["tab_index"] is None
    assert "catálogo" in details["roadmap"].lower()

def test_graphical_itil_map_loads_headless(tmp_path):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    import pytest
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication
    from itsm.itil_map import ITILMapDialog

    app = QApplication.instance() or QApplication([])
    dialog = ITILMapDialog()
    assert dialog.scene.items()
    assert not dialog.open_button.isEnabled() or dialog.current["key"] == "incident"
    dialog.show_detail("service_catalog")
    assert not dialog.open_button.isEnabled()
    dialog.show_detail("incident")
    assert dialog.open_button.isEnabled()
    dialog.close()
    assert app is not None
