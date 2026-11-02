"""Mapa das práticas ITIL (Version 5), navegável e integrado às abas disponíveis."""
from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QGraphicsScene, QGraphicsView, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QSplitter, QTextBrowser,
    QVBoxLayout, QWidget,
)

from itsm.itil_catalog import (
    GROUP_GENERAL, GROUP_PRODUCT, PRACTICES, counts,
    implementation_status, summary,
)

GROUPS = ((GROUP_PRODUCT, 15), (GROUP_GENERAL, 653))


def label_box(scene, x, y, width, height, text, fill, border):
    scene.addRect(
        x, y, width, height, QPen(QColor(border), 2), QBrush(QColor(fill))
    )
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    label.setStyleSheet("background: transparent; color: #eff6ff; "
                        "font-size: 15px; font-weight: 700;")
    proxy = scene.addWidget(label)
    proxy.setGeometry(x + 6, y + 5, width - 12, height - 10)


class ITILMapDialog(QDialog):
    """Representa grupos de práticas. As arestas NÃO implicam fluxo sequencial."""

    def __init__(self, parent=None, open_module=None):
        super().__init__(parent)
        self.open_module = open_module
        self.current = None
        self.setWindowTitle("ITIL (Version 5) | Mapa de práticas e roadmap")
        self.resize(1470, 880)

        layout = QVBoxLayout(self)
        title = QLabel("ITIL (Version 5) — mapa e evolução da ferramenta")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #eff6ff")
        layout.addWidget(title)

        stats = counts()
        description = QLabel(
            f"{stats['total']} práticas em dois grupos | "
            f"{stats['mvp']} com módulo MVP parcial | "
            f"{stats['planned']} ainda planejadas\n"
            "As conexões indicam o agrupamento das práticas, "
            "não uma sequência obrigatória de processos."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        legend = QHBoxLayout()
        for text, color in (
            ("● Núcleo funcional no MVP (parcial)", "#5edab0"),
            ("● Planejada (ainda não implementada)", "#aab9d2"),
        ):
            item = QLabel(text)
            item.setStyleSheet("color: " + color + "; font-weight: 650;")
            legend.addWidget(item)
        legend.addStretch()
        layout.addLayout(legend)

        bar = QHBoxLayout()
        for title, cb in (
            ("−", lambda: self.zoom(0.8)),
            ("+", lambda: self.zoom(1.25)),
            ("Ajustar diagrama", self.fit_map),
            ("Exportar roadmap CSV", self.export_csv),
        ):
            button = QPushButton(title)
            button.clicked.connect(cb)
            bar.addWidget(button)
        bar.addStretch()
        layout.addLayout(bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.scene = QGraphicsScene(self)
        self.scene.setBackgroundBrush(QBrush(QColor("#121b29")))
        self.scene.setSceneRect(0, 0, 1280, 1120)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        splitter.addWidget(self.view)

        sidebar = QWidget()
        sidebar.setMinimumWidth(290)
        details_layout = QVBoxLayout(sidebar)
        self.details_header = QLabel("Selecione uma prática")
        self.details_header.setWordWrap(True)
        self.details_header.setStyleSheet("font-size: 17px; font-weight: 700;")
        details_layout.addWidget(self.details_header)
        self.details = QTextBrowser()
        self.details.setReadOnly(True)
        details_layout.addWidget(self.details)
        self.open_button = QPushButton("Abrir módulo desta prática")
        self.open_button.clicked.connect(self.go_to_module)
        self.open_button.setEnabled(False)
        details_layout.addWidget(self.open_button)
        splitter.addWidget(sidebar)
        splitter.setSizes([1030, 315])
        layout.addWidget(splitter, 1)

        note = QLabel(
            "O mapa representa funcionalidades reais do software. "
            "Não constitui certificação ou conformidade com ITIL."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #aab8cf; font-size: 11px;")
        layout.addWidget(note)

        self.draw_map()
        self.fit_map()
        self.show_detail("incident")

    def draw_map(self):
        self.scene.clear()
        label_box(
            self.scene, 435, 18, 405, 75,
            "ITIL (Version 5)\n34 práticas de gerenciamento", "#234b72", "#67bef5"
        )
        pen = QPen(QColor("#536d8c"), 2)
        self.scene.addLine(638, 93, 638, 115, pen)
        self.scene.addLine(315, 115, 956, 115, pen)
        self.scene.addLine(315, 115, 315, 139, pen)
        self.scene.addLine(956, 115, 956, 139, pen)

        for group, x in GROUPS:
            practices = [p for p in PRACTICES if p.group == group]
            label_box(
                self.scene, x + 12, 139, 586, 63,
                f"{group}\n{len(practices)} práticas", "#293a53", "#7085a5"
            )
            trunks = (x + 34, x + 331)
            self.scene.addLine(x + 307, 202, x + 307, 221, pen)
            self.scene.addLine(trunks[0], 221, trunks[1], 221, pen)
            rows = (len(practices) + 1) // 2
            for trunk in trunks:
                self.scene.addLine(trunk, 221, trunk, 240 + (rows - 1) * 72 + 28, pen)
            for index, practice in enumerate(practices):
                row, col = divmod(index, 2)
                y = 240 + 72 * row
                left = x + (52 if col == 0 else 348)
                self.scene.addLine(trunks[col], y + 27, left, y + 27, pen)
                implemented = implementation_status(practice.key) == "mvp"
                text = (
                    practice.portuguese + "\n" +
                    ("Disponível · MVP" if implemented else "Planejada")
                )
                button = QPushButton(text)
                button.setFixedSize(243, 56)
                button.setToolTip(practice.name)
                button.setStyleSheet(
                    "QPushButton { text-align: center; padding: 4px; "
                    "font-size: 11px; font-weight: 600; color: #f4f7fc; "
                    "border: 2px solid " +
                    ("#51d5a9; background: #1b4739;" if implemented else
                     "#61718c; background: #2b3549;") +
                    " border-radius: 8px; }"
                    "QPushButton:hover { border-color: #a4dcff; background: #2a5574; }"
                )
                button.clicked.connect(
                    lambda checked=False, key=practice.key: self.show_detail(key)
                )
                item = self.scene.addWidget(button)
                item.setPos(left, y)

    def show_detail(self, key):
        data = summary(key)
        self.current = data
        self.details_header.setText(data["portuguese"])
        state = "Núcleo funcional MVP (parcial)" if data["status"] == "mvp" else "Planejada"
        self.details.setPlainText(
            f"Prática (EN)\n{data['name']}\n\n"
            f"Grupo\n{data['group']}\n\n"
            f"Situação\n{state}\n\n"
            f"O que existe hoje\n{data['delivered']}\n\n"
            f"Próximos incrementos\n{data['roadmap']}\n\n"
            "O status mede o software, não conformidade integral ITIL."
        )
        self.open_button.setEnabled(
            data["status"] == "mvp" and data["tab_index"] is not None
        )

    def go_to_module(self):
        if self.current and self.current["tab_index"] is not None:
            if callable(self.open_module):
                self.open_module(self.current["tab_index"])
                self.accept()

    def fit_map(self):
        self.view.fitInView(
            self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio
        )

    def zoom(self, factor):
        current = self.view.transform().m11()
        if 0.2 <= current * factor <= 2.5:
            self.view.scale(factor, factor)

    def export_csv(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, "Exportar roadmap ITIL", str(Path.home() / "ITIL5-roadmap.csv"),
            "CSV (*.csv)"
        )
        if not dest:
            return
        try:
            with open(dest, "w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream, delimiter=";")
                writer.writerow(
                    ("Grupo", "Prática (EN)", "Prática (PT)", "Status",
                     "Funcionalidades existentes", "Evolução prevista")
                )
                for practice in PRACTICES:
                    data = summary(practice.key)
                    writer.writerow(
                        (data["group"], data["name"], data["portuguese"],
                         data["status"], data["delivered"], data["roadmap"])
                    )
        except OSError as error:
            QMessageBox.critical(self, "Exportação", str(error))
