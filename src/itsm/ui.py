"""Interface desktop Windows para operação local do PT2VHF ITSM."""
from __future__ import annotations

import csv
import getpass
import json
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from itsm import db

STATUS_PT = {
    "new": "Novo", "triage": "Triagem", "in_progress": "Em andamento",
    "waiting": "Aguardando", "resolved": "Resolvido", "closed": "Encerrado",
    "reopened": "Reaberto", "cancelled": "Cancelado",
    "approval_pending": "Aguardando aprovação", "approved": "Aprovado",
    "rejected": "Rejeitado", "fulfilled": "Atendido", "draft": "Rascunho",
    "assessment": "Avaliação", "awaiting_approval": "Aguardando aprovação",
    "scheduled": "Agendado", "implementing": "Implementação",
    "rolled_back": "Revertido", "review": "Revisão",
    "investigating": "Investigação", "known_error": "Erro conhecido",
    "active": "Ativo", "stock": "Estoque", "maintenance": "Manutenção",
    "retired": "Desativado",
}

def display_status(value):
    return STATUS_PT.get(str(value), str(value))

def display_error(parent, exc):
    if isinstance(exc, sqlite3.IntegrityError):
        message = "Identificador duplicado ou referência inválida."
    else:
        message = str(exc)
    QMessageBox.critical(parent, "Operação não concluída", message)

def text_field(value=""):
    field = QLineEdit()
    field.setText(str(value or ""))
    return field

def selected_id(table):
    items = table.selectedItems()
    if not items:
        return None
    first = table.item(items[0].row(), 0)
    return first.data(Qt.ItemDataRole.UserRole) if first else None

def populate_table(table, columns, rows):
    table.setSortingEnabled(False)
    table.clear()
    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.setRowCount(len(rows))
    for row_idx, (record_id, values) in enumerate(rows):
        for col_idx, value in enumerate(values):
            cell = QTableWidgetItem(str(value if value is not None else ""))
            if col_idx == 0:
                cell.setData(Qt.ItemDataRole.UserRole, record_id)
            table.setItem(row_idx, col_idx, cell)
    table.resizeColumnsToContents()
    table.horizontalHeader().setStretchLastSection(True)
    table.setSortingEnabled(True)

def make_table():
    table = QTableWidget()
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    return table

class RecordEditor(QDialog):
    def __init__(self, parent, path, kind, record=None):
        super().__init__(parent)
        self.kind = kind
        self.setWindowTitle(("Editar" if record else "Novo") + " — " + db.KINDS[kind][1])
        self.resize(700, 660)
        record = record or {}
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.inputs = {}
        for key, title in (
            ("title", "Título *"), ("requester", "Solicitante"),
            ("assignee", "Responsável"), ("category", "Categoria"),
            ("target_at", "Prazo (AAAA-MM-DD)"),
        ):
            field = text_field(record.get(key))
            form.addRow(title, field)
            self.inputs[key] = field
        self.inputs["priority"] = QComboBox()
        self.inputs["priority"].addItems(db.PRIORITIES)
        self.inputs["priority"].setCurrentText(record.get("priority") or "P3")
        form.addRow("Prioridade", self.inputs["priority"])
        self.inputs["description"] = QTextEdit()
        self.inputs["description"].setPlainText(record.get("description") or "")
        self.inputs["description"].setMaximumHeight(90)
        form.addRow("Descrição", self.inputs["description"])

        assets = QComboBox()
        assets.addItem("Sem ativo relacionado", None)
        for asset in db.list_assets(path):
            assets.addItem(f"{asset['tag']} — {asset['name']}", asset["id"])
        assets.setCurrentIndex(max(0, assets.findData(record.get("asset_id"))))
        form.addRow("Ativo relacionado", assets)
        self.inputs["asset_id"] = assets

        if kind != "problem":
            problems = QComboBox()
            problems.addItem("Sem problema relacionado", None)
            for problem in db.list_records(path, "problem"):
                problems.addItem(f"{problem['code']} — {problem['title']}", problem["id"])
            problems.setCurrentIndex(max(0, problems.findData(record.get("problem_id"))))
            form.addRow("Problema relacionado", problems)
            self.inputs["problem_id"] = problems

        if kind == "change":
            for key, title in (
                ("risk", "Risco/impacto"), ("planned_start", "Início (AAAA-MM-DD)"),
                ("planned_end", "Fim (AAAA-MM-DD)"),
            ):
                field = text_field(record.get(key))
                form.addRow(title, field)
                self.inputs[key] = field
            for key, title in (
                ("implementation_plan", "Plano de implementação"),
                ("rollback_plan", "Plano de reversão"),
            ):
                field = QTextEdit()
                field.setMaximumHeight(75)
                field.setPlainText(record.get(key) or "")
                form.addRow(title, field)
                self.inputs[key] = field
        self.inputs["resolution"] = QTextEdit()
        self.inputs["resolution"].setPlainText(record.get("resolution") or "")
        self.inputs["resolution"].setMaximumHeight(75)
        form.addRow("Resolução / observações", self.inputs["resolution"])
        root.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self):
        data = {}
        for key, widget in self.inputs.items():
            if isinstance(widget, QTextEdit):
                data[key] = widget.toPlainText().strip()
            elif isinstance(widget, QComboBox):
                data[key] = widget.currentData() if key in ("asset_id", "problem_id") else widget.currentText()
            else:
                data[key] = widget.text().strip()
        return data

class AssetEditor(QDialog):
    FIELDS = (
        ("tag", "Patrimônio / ID *"), ("name", "Nome *"),
        ("asset_type", "Tipo"), ("serial", "Número de série"),
        ("owner", "Responsável"), ("location", "Localização"),
    )
    def __init__(self, parent, asset=None):
        super().__init__(parent)
        self.setWindowTitle("Ativo de TI")
        self.resize(560, 380)
        asset = asset or {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.fields = {}
        for key, label in self.FIELDS:
            field = text_field(asset.get(key))
            self.fields[key] = field
            form.addRow(label, field)
        self.fields["status"] = QComboBox()
        self.fields["status"].addItems(db.ASSET_STATUSES)
        self.fields["status"].setCurrentText(asset.get("status") or "active")
        form.addRow("Situação", self.fields["status"])
        self.fields["notes"] = QTextEdit()
        self.fields["notes"].setPlainText(asset.get("notes") or "")
        self.fields["notes"].setMaximumHeight(85)
        form.addRow("Observações", self.fields["notes"])
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        data = {}
        for key, widget in self.fields.items():
            data[key] = (widget.toPlainText() if isinstance(widget, QTextEdit) else
                         widget.currentText() if isinstance(widget, QComboBox) else
                         widget.text()).strip()
        return data

class DashboardTab(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        title = QLabel("Visão geral da operação")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        self.summary = QLabel()
        self.summary.setObjectName("dashboard")
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        hint = QLabel(
            "MVP offline: dados armazenados neste computador. "
            "A identificação do operador é declaratória; não há autenticação ou aprovação eletrônica segura."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()

    def refresh(self):
        stats = db.dashboard(self.window.path)
        self.summary.setText(
            "<h2>Operação</h2>"
            f"<p><b>Registros abertos:</b> {stats['open_records']} &nbsp;&nbsp; "
            f"<b>Prazos vencidos:</b> {stats['overdue']} &nbsp;&nbsp; "
            f"<b>Aprovações pendentes:</b> {stats['pending_approvals']}</p>"
            "<h2>Práticas</h2>"
            f"<p>Incidentes: <b>{stats['incident']}</b> &nbsp;&nbsp; "
            f"Requisições: <b>{stats['request']}</b> &nbsp;&nbsp; "
            f"Mudanças: <b>{stats['change']}</b> &nbsp;&nbsp; "
            f"Problemas: <b>{stats['problem']}</b></p>"
            f"<p>Ativos em operação: <b>{stats['active_assets']}</b></p>"
        )

class RecordsTab(QWidget):
    def __init__(self, window, kind):
        super().__init__()
        self.window = window
        self.kind = kind
        layout = QVBoxLayout(self)
        title = QLabel(db.KINDS[kind][1])
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtrar por código, título, solicitante ou responsável")
        toolbar.addWidget(self.search, 1)
        for label, callback in (
            ("Novo", self.create), ("Editar", self.edit),
            ("Alterar estado", self.change_status),
            ("Aprovar", lambda: self.approve(True)),
            ("Rejeitar", lambda: self.approve(False)),
            ("Atualizar", self.refresh),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
            if label in ("Aprovar", "Rejeitar") and kind not in ("request", "change"):
                button.hide()
        layout.addLayout(toolbar)
        self.table = make_table()
        layout.addWidget(self.table)
        self.search.textChanged.connect(self.refresh)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit())

    def refresh(self, *_):
        records = db.list_records(self.window.path, self.kind, self.search.text().strip())
        rows = []
        for item in records:
            rows.append((item["id"], (
                item["code"], item["title"], display_status(item["status"]),
                item["priority"], item["requester"], item["assignee"],
                item["asset_tag"] or "", item["updated_at"][:16].replace("T", " "),
            )))
        populate_table(self.table,
                       ("Código", "Título", "Estado", "Prioridade", "Solicitante",
                        "Responsável", "Ativo", "Atualizado (UTC)"), rows)

    def selected(self):
        item_id = selected_id(self.table)
        if item_id is None:
            QMessageBox.information(self, "Seleção", "Selecione um registro.")
        return item_id

    def create(self):
        dialog = RecordEditor(self, self.window.path, self.kind)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                db.create_record(self.window.path, self.kind, dialog.values(),
                                 self.window.actor_name())
                self.window.refresh_all()
            except (ValueError, sqlite3.Error) as exc:
                display_error(self, exc)

    def edit(self):
        item_id = self.selected()
        if item_id is None:
            return
        record = db.get_record(self.window.path, item_id)
        dialog = RecordEditor(self, self.window.path, self.kind, record)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                db.update_record(self.window.path, item_id, dialog.values(),
                                 self.window.actor_name())
                self.window.refresh_all()
            except (ValueError, sqlite3.Error) as exc:
                display_error(self, exc)

    def change_status(self):
        item_id = self.selected()
        if item_id is None:
            return
        record = db.get_record(self.window.path, item_id)
        choices = db.allowed_next(record)
        if not choices:
            QMessageBox.information(
                self, "Fluxo", "Não há transições disponíveis. Verifique a aprovação ou o encerramento."
            )
            return
        labels = [f"{display_status(code)} [{code}]" for code in choices]
        choice, ok = QInputDialog.getItem(self, "Alterar estado", "Próximo estado:",
                                          labels, 0, False)
        if not ok:
            return
        next_state = choices[labels.index(choice)]
        try:
            db.set_status(self.window.path, item_id, next_state, self.window.actor_name())
            self.window.refresh_all()
        except (ValueError, sqlite3.Error) as exc:
            display_error(self, exc)

    def approve(self, is_approved):
        item_id = self.selected()
        if item_id is None:
            return
        approver, ok = QInputDialog.getText(
            self, "Decisão de aprovação", "Identificação do aprovador:",
            text=self.window.actor_name(),
        )
        if not ok:
            return
        try:
            db.decide_approval(self.window.path, item_id, is_approved, approver)
            self.window.refresh_all()
        except (ValueError, sqlite3.Error) as exc:
            display_error(self, exc)

class AssetsTab(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        title = QLabel("Ativos de TI")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtrar por patrimônio, nome, série ou responsável")
        toolbar.addWidget(self.search, 1)
        for label, callback in (("Novo ativo", self.create),
                                ("Editar ativo", self.edit), ("Atualizar", self.refresh)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        layout.addLayout(toolbar)
        self.table = make_table()
        layout.addWidget(self.table)
        self.search.textChanged.connect(self.refresh)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit())

    def refresh(self, *_):
        records = db.list_assets(self.window.path, self.search.text().strip())
        populate_table(self.table,
                       ("ID", "Patrimônio", "Nome", "Tipo", "Série", "Responsável",
                        "Localização", "Situação"),
                       [(row["id"], (row["id"], row["tag"], row["name"], row["asset_type"],
                                       row["serial"], row["owner"], row["location"],
                                       display_status(row["status"]))) for row in records])

    def create(self):
        editor = AssetEditor(self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            try:
                db.create_asset(self.window.path, editor.values(), self.window.actor_name())
                self.window.refresh_all()
            except (ValueError, sqlite3.Error) as exc:
                display_error(self, exc)

    def edit(self):
        asset_id = selected_id(self.table)
        if asset_id is None:
            QMessageBox.information(self, "Seleção", "Selecione um ativo.")
            return
        editor = AssetEditor(self, db.get_asset(self.window.path, asset_id))
        if editor.exec() == QDialog.DialogCode.Accepted:
            try:
                db.update_asset(self.window.path, asset_id, editor.values(),
                                self.window.actor_name())
                self.window.refresh_all()
            except (ValueError, sqlite3.Error) as exc:
                display_error(self, exc)

class HistoryTab(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        title = QLabel("Trilha de alterações (últimos 300 eventos)")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        self.table = make_table()
        layout.addWidget(self.table)
        detail = QPushButton("Visualizar detalhes do evento")
        detail.clicked.connect(self.details)
        layout.addWidget(detail)
        self.events = []

    def refresh(self):
        self.events = db.list_audit(self.window.path)
        populate_table(self.table,
                       ("Evento", "Data UTC", "Entidade", "ID", "Ação", "Operador"),
                       [(event["id"], (event["id"], event["created_at"],
                                       event["entity_type"], event["entity_id"],
                                       event["action"], event["actor"])) for event in self.events])

    def details(self):
        event_id = selected_id(self.table)
        event = next((e for e in self.events if e["id"] == event_id), None)
        if event is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Auditoria #{event_id}")
        dlg.resize(720, 520)
        layout = QVBoxLayout(dlg)
        area = QTextEdit()
        area.setReadOnly(True)
        data = {
            "Evento": event["action"], "Operador": event["actor"],
            "Antes": json.loads(event["before_json"]),
            "Depois": json.loads(event["after_json"]),
        }
        area.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))
        layout.addWidget(area)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        dlg.exec()

class MainWindow(QMainWindow):
    def __init__(self, path):
        super().__init__()
        self.path = Path(path)
        self.setWindowTitle("PT2VHF ITSM | Gestão de Serviços")
        self.resize(1450, 840)
        central = QWidget()
        shell = QVBoxLayout(central)
        head = QHBoxLayout()
        product = QLabel("PT2VHF  /  ITSM")
        product.setObjectName("brand")
        head.addWidget(product)
        head.addStretch()
        head.addWidget(QLabel("Operador (auditoria local):"))
        self.operator = text_field(getpass.getuser())
        self.operator.setMaximumWidth(220)
        head.addWidget(self.operator)
        shell.addLayout(head)
        self.tabs = QTabWidget()
        self.pages = [DashboardTab(self)]
        for kind in ("incident", "request", "change", "problem"):
            self.pages.append(RecordsTab(self, kind))
        self.pages.append(AssetsTab(self))
        self.pages.append(HistoryTab(self))
        for name, page in zip(
            ("Painel", "Incidentes", "Requisições", "Mudanças", "Problemas", "Ativos", "Histórico"),
            self.pages,
        ):
            self.tabs.addTab(page, name)
        shell.addWidget(self.tabs)
        self.setCentralWidget(central)
        self.tabs.currentChanged.connect(lambda *_: self.tabs.currentWidget().refresh())

        file_menu = self.menuBar().addMenu("Arquivo")
        backup_action = QAction("Fazer backup do banco...", self)
        backup_action.triggered.connect(self.backup)
        file_menu.addAction(backup_action)
        csv_action = QAction("Exportar aba para CSV...", self)
        csv_action.triggered.connect(self.export_csv)
        file_menu.addAction(csv_action)
        itil_menu = self.menuBar().addMenu("ITIL")
        map_action = QAction("ITIL (Version 5) | Mapa das 34 práticas", self)
        map_action.triggered.connect(self.show_itil_map)
        itil_menu.addAction(map_action)
        self.statusBar().showMessage(f"Base local: {self.path}")
        self.refresh_all()

    def show_itil_map(self):
        from itsm.itil_map import ITILMapDialog
        dialog = ITILMapDialog(
            self, open_module=lambda index: self.tabs.setCurrentIndex(index)
        )
        dialog.exec()

    def actor_name(self):
        return self.operator.text().strip() or "local"

    def refresh_all(self):
        for page in self.pages:
            page.refresh()

    def backup(self):
        target, _ = QFileDialog.getSaveFileName(
            self, "Backup SQLite", str(Path.home() / "ITSM-backup.db"),
            "Bancos SQLite (*.db)"
        )
        if not target:
            return
        try:
            if Path(target).resolve() == self.path.resolve():
                raise ValueError("O destino deve ser diferente do banco ativo.")
            with sqlite3.connect(self.path) as origin, sqlite3.connect(target) as dest:
                origin.backup(dest)
            QMessageBox.information(self, "Backup", f"Backup criado:\n{target}")
        except (OSError, sqlite3.Error, ValueError) as exc:
            display_error(self, exc)

    def export_csv(self):
        widget = self.tabs.currentWidget()
        if not hasattr(widget, "table"):
            QMessageBox.information(self, "Exportação", "Selecione uma aba com dados.")
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "Exportar CSV", str(Path.home() / "ITSM-export.csv"), "CSV (*.csv)"
        )
        if not target:
            return
        try:
            table = widget.table
            with open(target, "w", newline="", encoding="utf-8-sig") as stream:
                out = csv.writer(stream, delimiter=";")
                out.writerow([table.horizontalHeaderItem(i).text()
                              for i in range(table.columnCount())])
                for i in range(table.rowCount()):
                    out.writerow([table.item(i, j).text() if table.item(i, j) else ""
                                  for j in range(table.columnCount())])
            QMessageBox.information(self, "Exportação", f"CSV criado:\n{target}")
        except OSError as exc:
            display_error(self, exc)

STYLESHEET = """
QMainWindow, QWidget { background: #151b27; color: #e9edf5; font-size: 12px; }
QLabel#brand { font-size: 22px; font-weight: 700; color: #65d0ee; margin: 10px 0; }
QLabel#pageTitle { font-size: 21px; font-weight: 650; margin: 8px 0; }
QLabel#dashboard { line-height: 1.5; padding: 16px; background: #202b3b;
                   border-radius: 12px; font-size: 16px; }
QPushButton { background: #226da2; border: 1px solid #328cbd; border-radius: 6px;
              padding: 8px 12px; color: white; }
QPushButton:hover { background: #3484b8; }
QLineEdit, QTextEdit, QComboBox, QTableWidget {
    background: #202b3b; color: #e9edf5; border: 1px solid #405068;
    border-radius: 5px; padding: 5px; selection-background-color: #2774ab;
}
QHeaderView::section { background: #29364a; color: #e9edf5; padding: 8px; border: 0; }
QTabBar::tab { background: #263448; color: #d2dce8; padding: 12px 17px; margin-right: 3px; }
QTabBar::tab:selected { background: #226da2; color: white; }
QMenuBar, QMenu, QStatusBar { background: #202b3b; color: #e9edf5; }
"""

def run(path):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("PT2VHF ITSM")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow(path)
    window.show()
    return app.exec()
