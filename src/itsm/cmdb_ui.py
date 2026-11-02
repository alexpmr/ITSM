"""Interface CMDB: itens, vínculos, análise de impacto e seleção transversal de CIs."""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)
from itsm import cmdb, db

CI_LABELS = {
    "business_service": "Serviço de negócio",
    "technical_service": "Serviço técnico", "application": "Aplicação",
    "server": "Servidor", "database": "Banco de dados", "network": "Rede",
    "cloud": "Nuvem", "container": "Container", "endpoint": "Estação",
    "other": "Outro",
}
STATUS = {
    "planned": "Planejado", "active": "Ativo",
    "maintenance": "Manutenção", "retired": "Desativado",
}
ENVIRONMENT = {
    "production": "Produção", "staging": "Homologação",
    "development": "Desenvolvimento", "test": "Teste", "other": "Outro",
}
CRITICALITY = {
    "low": "Baixa", "medium": "Média", "high": "Alta", "critical": "Crítica",
}
RELATIONS = {
    "depends_on": "Depende de (origem → destino)",
    "hosted_on": "Hospedado em (origem → destino)",
    "supports": "Suporta (origem → destino)",
    "connects_to": "Conectado a (sem propagação de impacto)",
}
LINK_ROLES = {"affected": "Afetado", "target": "Alvo", "related": "Relacionado"}


def combo(items, selected=None):
    field = QComboBox()
    for key, label in items.items():
        field.addItem(label, key)
    position = field.findData(selected)
    if position >= 0:
        field.setCurrentIndex(position)
    return field


def selected_id(table):
    indexes = table.selectionModel().selectedRows()
    if not indexes:
        return None
    cell = table.item(indexes[0].row(), 0)
    return cell.data(Qt.ItemDataRole.UserRole) if cell else None


def build_table(columns):
    table = QTableWidget()
    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(False)
    table.verticalHeader().hide()
    table.horizontalHeader().setStretchLastSection(True)
    return table


def fill(table, rows):
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for i, (item_id, values) in enumerate(rows):
        for j, value in enumerate(values):
            cell = QTableWidgetItem(str(value if value is not None else ""))
            if j == 0:
                cell.setData(Qt.ItemDataRole.UserRole, item_id)
            table.setItem(i, j, cell)
    table.resizeColumnsToContents()
    table.setSortingEnabled(True)


class CIEditor(QDialog):
    TEXT_FIELDS = (
        ("code", "Código único *"), ("name", "Nome *"),
        ("service_name", "Serviço relacionado (texto temporário)"),
        ("owner", "Responsável"), ("location", "Localização"),
        ("description", "Descrição"),
    )

    def __init__(self, parent, path, item=None):
        super().__init__(parent)
        self.setWindowTitle("Editar CI" if item else "Novo item de configuração")
        self.resize(680, 450)
        item = item or {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.controls = {}
        for key, label in self.TEXT_FIELDS:
            entry = QLineEdit(str(item.get(key) or ""))
            self.controls[key] = entry
            form.addRow(label, entry)
        for key, label, opts, default in (
            ("ci_type", "Classe", CI_LABELS, "other"),
            ("status", "Situação", STATUS, "active"),
            ("environment", "Ambiente", ENVIRONMENT, "production"),
            ("criticality", "Criticidade", CRITICALITY, "medium"),
        ):
            entry = combo(opts, item.get(key) or default)
            self.controls[key] = entry
            form.addRow(label, entry)
        assets = QComboBox()
        assets.addItem("Nenhum vínculo patrimonial", None)
        for asset in db.list_assets(path):
            assets.addItem(f"{asset['tag']} — {asset['name']}", asset["id"])
        assets.setCurrentIndex(max(0, assets.findData(item.get("asset_id"))))
        self.controls["asset_id"] = assets
        form.addRow("Ativo do inventário (opcional)", assets)
        layout.addLayout(form)
        explanation = QLabel(
            "CMDB modela componentes de serviços e dependências; ITAM registra ativos "
            "patrimoniais. O vínculo é opcional e 1:1 no MVP. O nome do serviço "
            "é provisório até a implantação do catálogo de serviços."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return {
            key: field.currentData() if isinstance(field, QComboBox) else field.text().strip()
            for key, field in self.controls.items()
        }


class RelationEditor(QDialog):
    def __init__(self, parent, path):
        super().__init__(parent)
        self.setWindowTitle("Relacionar itens de configuração")
        self.resize(590, 260)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        cis = cmdb.list_cis(path)
        self.source = QComboBox()
        self.target = QComboBox()
        for item in cis:
            display = f"{item['code']} — {item['name']}"
            self.source.addItem(display, item["id"])
            self.target.addItem(display, item["id"])
        if self.target.count() > 1:
            self.target.setCurrentIndex(1)
        self.kind = combo(RELATIONS, "depends_on")
        form.addRow("CI de origem", self.source)
        form.addRow("Relacionamento", self.kind)
        form.addRow("CI de destino", self.target)
        layout.addLayout(form)
        note = QLabel(
            "Exemplo: aplicação DEPENDE DE banco de dados; servidor HOSPEDADO EM "
            "plataforma; balanceador SUPORTA aplicação. A análise de impacto "
            "considera dependências direcionais e evita ciclos."
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
        return self.source.currentData(), self.target.currentData(), self.kind.currentData()


class CIChooser(QDialog):
    """Seleção M:N dos CIs para incidentes, requisições, problemas e mudanças."""

    def __init__(self, parent, path, existing=(), kind="incident"):
        super().__init__(parent)
        self.setWindowTitle("CIs relacionados ao registro")
        self.resize(690, 600)
        default_role = "target" if kind == "change" else "affected"
        current = dict(existing)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Marque os CIs e identifique seu papel no registro. "
            "Em mudanças, normalmente use 'Alvo'; em incidentes, 'Afetado'."
        ))
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(("Vincular", "Código", "Nome / tipo", "Papel"))
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.controls = []
        items = cmdb.list_cis(path, include_retired=True)
        self.table.setRowCount(len(items))
        for i, item in enumerate(items):
            check = QCheckBox()
            check.setChecked(item["id"] in current)
            self.table.setCellWidget(i, 0, check)
            self.table.setItem(i, 1, QTableWidgetItem(item["code"]))
            self.table.setItem(i, 2, QTableWidgetItem(
                f"{item['name']} ({CI_LABELS.get(item['ci_type'], item['ci_type'])})"
            ))
            role = combo(LINK_ROLES, current.get(item["id"], default_role))
            self.table.setCellWidget(i, 3, role)
            self.controls.append((item["id"], check, role))
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return [
            (ci_id, role.currentData()) for ci_id, check, role in self.controls
            if check.isChecked()
        ]


class CMDBTab(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self._items = []
        root = QVBoxLayout(self)
        title = QLabel("CMDB | Gestão da Configuração de Serviços")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        self.stats = QLabel()
        root.addWidget(self.stats)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Pesquisar CI, serviço, classe ou responsável")
        toolbar.addWidget(self.search, 1)
        for name, fn in (
            ("Novo CI", self.create_ci), ("Editar CI", self.edit_ci),
            ("Relacionar CIs", self.create_relation),
            ("Remover vínculo", self.delete_relation),
            ("Analisar impacto", self.analyze),
            ("Atualizar", self.refresh),
        ):
            button = QPushButton(name)
            button.clicked.connect(fn)
            toolbar.addWidget(button)
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Vertical)
        cis_box = QWidget()
        c_layout = QVBoxLayout(cis_box)
        c_layout.addWidget(QLabel("Itens de configuração"))
        self.table = build_table(
            ("Código", "Nome", "Classe", "Ambiente", "Criticidade", "Situação",
             "Serviço", "Ativo ITAM", "Registros", "ID")
        )
        c_layout.addWidget(self.table)
        splitter.addWidget(cis_box)
        relations_box = QWidget()
        r_layout = QVBoxLayout(relations_box)
        r_layout.addWidget(QLabel("Dependências e relacionamentos (origem → destino)"))
        self.relations_table = build_table(("Origem", "Relação", "Destino"))
        r_layout.addWidget(self.relations_table)
        splitter.addWidget(relations_box)
        splitter.setSizes([440, 170])
        root.addWidget(splitter, 1)

        root.addWidget(QLabel("Análise de impacto: selecione o CI de origem e clique em Analisar impacto"))
        self.impact_view = QTextBrowser()
        self.impact_view.setMinimumHeight(125)
        root.addWidget(self.impact_view)
        self.search.textChanged.connect(self.refresh)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit_ci())

    def refresh(self, *_):
        self._items = cmdb.list_cis(self.window.path, self.search.text().strip())
        stats = cmdb.stats(self.window.path)
        self.stats.setText(
            f"CIs: {stats['cis']}  |  Ativos: {stats['active']}  |  "
            f"Relações: {stats['relations']}  |  Registros vinculados: {stats['linked_records']}"
        )
        fill(self.table, [
            (ci["id"], (
                ci["code"], ci["name"], CI_LABELS.get(ci["ci_type"], ci["ci_type"]),
                ENVIRONMENT.get(ci["environment"], ci["environment"]),
                CRITICALITY.get(ci["criticality"], ci["criticality"]),
                STATUS.get(ci["status"], ci["status"]), ci["service_name"],
                ci["asset_tag"] or "", ci["record_count"], ci["id"]
            ))
            for ci in self._items
        ])
        fill(self.relations_table, [
            (rel["id"], (
                rel["source_code"], rel["relation_type"], rel["target_code"]
            ))
            for rel in cmdb.list_relations(self.window.path)
        ])

    def require_ci(self):
        result = selected_id(self.table)
        if result is None:
            QMessageBox.information(self, "CMDB", "Selecione um CI.")
        return result

    def create_ci(self):
        dlg = CIEditor(self, self.window.path)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                cmdb.create_ci(self.window.path, dlg.values(), self.window.actor_name())
                self.window.refresh_all()
            except (ValueError, sqlite3.Error) as exc:
                QMessageBox.critical(self, "CMDB", str(exc))

    def edit_ci(self):
        ci_id = self.require_ci()
        if ci_id is None:
            return
        dlg = CIEditor(self, self.window.path, cmdb.get_ci(self.window.path, ci_id))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                cmdb.update_ci(self.window.path, ci_id, dlg.values(), self.window.actor_name())
                self.window.refresh_all()
            except (ValueError, sqlite3.Error) as exc:
                QMessageBox.critical(self, "CMDB", str(exc))

    def create_relation(self):
        if len(cmdb.list_cis(self.window.path)) < 2:
            QMessageBox.information(self, "CMDB", "Cadastre pelo menos dois CIs.")
            return
        dlg = RelationEditor(self, self.window.path)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                cmdb.add_relation(
                    self.window.path, *dlg.values(), actor=self.window.actor_name()
                )
                self.window.refresh_all()
            except (ValueError, sqlite3.Error) as exc:
                QMessageBox.critical(self, "CMDB", str(exc))

    def delete_relation(self):
        relation_id = selected_id(self.relations_table)
        if relation_id is None:
            QMessageBox.information(self, "CMDB", "Selecione um relacionamento.")
            return
        if QMessageBox.question(
            self, "Excluir relacionamento", "Remover este vínculo da CMDB?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            cmdb.remove_relation(self.window.path, relation_id, self.window.actor_name())
            self.window.refresh_all()
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "CMDB", str(exc))

    def analyze(self):
        ci_id = self.require_ci()
        if ci_id is None:
            return
        report = cmdb.impact(self.window.path, ci_id)
        lines = [
            "ANÁLISE DE IMPACTO ESTIMADO",
            "Propagação: depende de / hospedado em / suporta. "
            "Conexão física não implica impacto.",
            "",
            "CIs potencialmente afetados:",
        ]
        for ci in report["cis"]:
            indent = "  " * ci["depth"]
            lines.append(
                f"{indent}{ci['code']} — {ci['name']} "
                f"[{CRITICALITY.get(ci['criticality'], ci['criticality'])}]"
            )
        lines.extend(("", "Registros associados aos CIs considerados:"))
        if not report["records"]:
            lines.append("Nenhum registro vinculado.")
        for record in report["records"]:
            lines.append(
                f"{record['code']} — {record['title']} | via {record['via_ci']} "
                f"({LINK_ROLES.get(record['link_type'], record['link_type'])})"
            )
        lines.extend(("", "Nota: este resultado é topológico, não uma comprovação "
                         "de indisponibilidade ou de causalidade."))
        self.impact_view.setPlainText("\n".join(lines))
