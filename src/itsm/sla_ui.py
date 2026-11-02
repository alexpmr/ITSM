"""Configuração de políticas e visão de conformidade SLA no desktop Windows."""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QAbstractItemView,
)

from itsm import db, sla

PRACTICE_LABELS = {"*": "Todas", **{key: label for key, (_prefix, label) in db.KINDS.items()}}


class PolicyEditor(QDialog):
    FIELDS = (
        ("code", "Código *"), ("name", "Nome da política *"),
        ("response_minutes", "Resposta (min) *"),
        ("resolution_minutes", "Resolução (min) *"),
        ("start_hour", "Início do expediente HH:MM"),
        ("end_hour", "Fim do expediente HH:MM"),
        ("weekdays", "Dias úteis (0=seg a 6=dom)"),
        ("holidays", "Feriados AAAA-MM-DD, separados por vírgula"),
        ("pause_states", "Estados de pausa separados por vírgula"),
    )

    def __init__(self, parent=None, policy=None):
        super().__init__(parent)
        self.setWindowTitle("Política de SLA")
        self.resize(660, 560)
        source = policy or {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.inputs = {}
        self.inputs["kind"] = QComboBox()
        for key, label in PRACTICE_LABELS.items():
            self.inputs["kind"].addItem(label, key)
        self.inputs["kind"].setCurrentIndex(max(
            0, self.inputs["kind"].findData(source.get("kind") or "*")
        ))
        form.addRow("Prática aplicável *", self.inputs["kind"])
        self.inputs["priority"] = QComboBox()
        for key in ("*", *db.PRIORITIES):
            self.inputs["priority"].addItem("Todas" if key == "*" else key, key)
        self.inputs["priority"].setCurrentIndex(max(
            0, self.inputs["priority"].findData(source.get("priority") or "*")
        ))
        form.addRow("Prioridade *", self.inputs["priority"])
        self.inputs["calendar"] = QComboBox()
        self.inputs["calendar"].addItem("24x7 — minutos contínuos", "24x7")
        self.inputs["calendar"].addItem("Horário útil — com calendário", "business")
        self.inputs["calendar"].setCurrentIndex(max(
            0, self.inputs["calendar"].findData(source.get("calendar") or "business")
        ))
        form.addRow("Calendário", self.inputs["calendar"])
        defaults = {
            "response_minutes": "60", "resolution_minutes": "480",
            "start_hour": "09:00", "end_hour": "18:00", "weekdays": "0,1,2,3,4",
            "holidays": "",
            "pause_states": "",
        }
        for key, label in self.FIELDS:
            field = QLineEdit()
            field.setText(str(source.get(key, defaults.get(key, ""))))
            if key == "pause_states" and source.get(key) and str(source[key]).startswith("["):
                import json
                field.setText(", ".join(json.loads(source[key])))
            self.inputs[key] = field
            form.addRow(label, field)

        self.inputs["active"] = QCheckBox("Política ativa — elegível para novas atribuições")
        self.inputs["active"].setChecked(bool(source.get("active", 1)))
        form.addRow("", self.inputs["active"])
        layout.addLayout(form)
        note = QLabel(
            "As regras são atribuídas automaticamente aos novos registros compatíveis. "
            "Registros antigos mantêm seu SLA original (snapshot) até reassociação manual. "
            "Valores iniciais do formulário são apenas exemplos — configure metas contratadas."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        result = {}
        for key, widget in self.inputs.items():
            if isinstance(widget, QComboBox):
                result[key] = widget.currentData()
            elif isinstance(widget, QCheckBox):
                result[key] = widget.isChecked()
            else:
                result[key] = widget.text().strip()
        return result


class SLATab(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        root = QVBoxLayout(self)
        title = QLabel("Gestão de Níveis de Serviço (SLA)")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        hint = QLabel(
            "Políticas centrais por prática e prioridade. Medição por calendário local, "
            "pausas por estado e avaliação de resposta/resolução dos registros operacionais."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)
        self.summary = QLabel()
        self.summary.setStyleSheet("padding: 12px; color: #bce8d6; font-weight: 600;")
        root.addWidget(self.summary)
        buttons = QHBoxLayout()
        for name, cb in (
            ("Nova política", self.new),
            ("Editar política", self.edit),
            ("Atualizar", self.refresh),
        ):
            btn = QPushButton(name)
            btn.clicked.connect(cb)
            buttons.addWidget(btn)
        buttons.addStretch()
        root.addLayout(buttons)
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            ("Código", "Nome", "Prática", "Prioridade", "Resposta", "Resolução",
             "Calendário", "Status", "ID")
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit())
        self.rows = []

    def refresh(self):
        self.rows = sla.list_policies(self.window.path)
        overview = sla.overview(self.window.path)
        self.summary.setText(
            f"Registros com SLA: {overview['assigned']}  |  "
            f"Em atendimento: {overview['active']}  |  "
            f"Violados: {overview['breached']}  |  "
            f"Em pausa: {overview['paused']}"
        )
        self.table.setRowCount(len(self.rows))
        for i, item in enumerate(self.rows):
            values = (
                item["code"], item["name"], PRACTICE_LABELS.get(item["kind"], item["kind"]),
                item["priority"], f"{item['response_minutes']} min",
                f"{item['resolution_minutes']} min", item["calendar"],
                "Ativa" if item["active"] else "Inativa", item["id"],
            )
            for j, val in enumerate(values):
                cell = QTableWidgetItem(str(val))
                if j == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item["id"])
                self.table.setItem(i, j, cell)
        self.table.resizeColumnsToContents()

    def selected(self):
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self, "SLA", "Selecione uma política.")
            return None
        cell = self.table.item(selected[0].row(), 0)
        return cell.data(Qt.ItemDataRole.UserRole) if cell else None

    def new(self):
        editor = PolicyEditor(self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            try:
                sla.create_policy(
                    self.window.path, editor.values(), self.window.actor_name()
                )
                self.window.refresh_all()
            except (ValueError, sqlite3.Error) as error:
                QMessageBox.critical(self, "Erro ao salvar SLA", str(error))

    def edit(self):
        policy_id = self.selected()
        if policy_id is None:
            return
        editor = PolicyEditor(self, sla.get_policy(self.window.path, policy_id))
        if editor.exec() == QDialog.DialogCode.Accepted:
            try:
                sla.update_policy(
                    self.window.path, policy_id, editor.values(), self.window.actor_name()
                )
                self.window.refresh_all()
            except (ValueError, sqlite3.Error) as error:
                QMessageBox.critical(self, "Erro ao alterar SLA", str(error))
