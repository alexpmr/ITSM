"""Catálogo público de nomes das 34 práticas ITIL (Version 5).

O mapa representa funcionalidades da aplicação e NÃO certificação de conformidade.
Nomes oficiais são apenas referências terminológicas; notas de escopo são autorais.
"""
from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class Practice:
    key: str
    name: str
    portuguese: str
    group: str
    version: str = "5"

GROUP_PRODUCT = "Gestão de produtos e serviços"
GROUP_GENERAL = "Gestão geral"

# ITIL (Version 5) consolidou as antigas 3 categorias em 2: 22 + 12.
PRODUCT_SERVICE = (
    ("availability", "Availability management", "Gestão da disponibilidade"),
    ("business_analysis", "Business analysis", "Análise de negócios"),
    ("capacity_performance", "Capacity and performance management", "Gestão de capacidade e desempenho"),
    ("change", "Change enablement", "Habilitação de mudanças"),
    ("deployment", "Deployment management", "Gestão de implantação"),
    ("incident", "Incident management", "Gestão de incidentes"),
    ("information_security", "Information security management", "Gestão de segurança da informação"),
    ("infrastructure_platform", "Infrastructure and platform management", "Gestão de infraestrutura e plataformas"),
    ("itam", "IT asset management", "Gestão de ativos de TI"),
    ("monitoring_event", "Monitoring and event management", "Monitoramento e gestão de eventos"),
    ("problem", "Problem management", "Gestão de problemas"),
    ("release", "Release management", "Gestão de liberações"),
    ("service_catalog", "Service catalog management", "Gestão do catálogo de serviços"),
    ("service_configuration", "Service configuration management", "Gestão da configuração de serviços"),
    ("service_continuity", "Service continuity management", "Gestão da continuidade de serviços"),
    ("service_design", "Service design", "Desenho de serviços"),
    ("service_desk", "Service desk", "Central de serviços"),
    ("service_financial", "Service financial management", "Gestão financeira de serviços"),
    ("service_level", "Service level management", "Gestão de níveis de serviço"),
    ("request", "Service request management", "Gestão de requisições de serviço"),
    ("service_validation_testing", "Service validation and testing", "Validação e testes de serviços"),
    ("software_development", "Software development and management", "Desenvolvimento e gestão de software"),
)
GENERAL = (
    ("architecture", "Architecture management", "Gestão de arquitetura"),
    ("continual_improvement", "Continual improvement", "Melhoria contínua"),
    ("knowledge", "Knowledge management", "Gestão do conhecimento"),
    ("measurement_reporting", "Measurement and reporting", "Medição e relatórios"),
    ("organizational_change", "Organizational change management", "Gestão de mudanças organizacionais"),
    ("portfolio", "Portfolio management", "Gestão de portfólio"),
    ("project", "Project management", "Gestão de projetos"),
    ("relationship", "Relationship management", "Gestão de relacionamento"),
    ("risk", "Risk management", "Gestão de riscos"),
    ("strategy", "Strategy management", "Gestão de estratégia"),
    ("supplier", "Supplier management", "Gestão de fornecedores"),
    ("workforce_talent", "Workforce and talent management", "Gestão de pessoas e talentos"),
)

PRACTICES = tuple(
    Practice(key, name, pt, GROUP_PRODUCT) for key, name, pt in PRODUCT_SERVICE
) + tuple(
    Practice(key, name, pt, GROUP_GENERAL) for key, name, pt in GENERAL
)
BY_KEY = {p.key: p for p in PRACTICES}

# Manter apenas chaves cujo fluxo está realmente disponível no sistema.
# "mvp" significa capacidade implementada em escopo reduzido,
# NÃO conformidade completa com o guia ITIL.
IMPLEMENTED_MVP = frozenset(("incident", "request", "change", "problem", "itam"))

# Mapeia prática para aba funcional existente; índice é aplicado no main window.
MODULE_TABS = {"incident": 1, "request": 2, "change": 3, "problem": 4, "itam": 5}

# Sumários escritos para refletir SOMENTE o que foi programado nesta versão.
DELIVERED = {
    "incident": (
        "Registro de incidentes, classificação e prioridade informadas pelo operador, "
        "triagem, execução, espera, resolução, reabertura, encerramento e histórico."
    ),
    "request": (
        "Abertura e acompanhamento de requisições, encaminhamento, aprovação declaratória, "
        "atendimento, reabertura e encerramento."
    ),
    "change": (
        "Avaliação, aprovação declaratória, janela planejada, exigência de planos de "
        "implementação e reversão, execução, rollback e revisão."
    ),
    "problem": (
        "Abertura de problemas, investigação, identificação de erro conhecido, "
        "resolução, reabertura e relacionamento com registros."
    ),
    "itam": (
        "Inventário local com patrimônio, tipo, série, proprietário, localização, "
        "estado do ativo e vínculo com registros de atendimento."
    ),
}
NEXT_STEPS = {
    "incident": "SLA, incidente maior, matriz impacto x urgência, escalonamentos e vinculação a serviços.",
    "request": "Catálogo de serviços, formulários parametrizáveis, aprovações com identidade verificada e automação.",
    "change": "CAB, tipos normal/padrão/emergencial, calendário, análise de risco e avaliação pós-implementação.",
    "problem": "Causa-raiz, workaround, KEDB, identificação de tendências e vínculos com mudanças.",
    "itam": "Ciclo de vida completo, contratos, garantias, importação, descoberta, reconciliação e CMDB separada.",
    "service_level": "SLAs/OLAs, calendários, metas por serviço e monitoramento de desempenho.",
    "service_catalog": "Catálogo configurável, modelos de requisição, aprovações e ciclos de publicação.",
    "service_configuration": "Modelo de CIs, relacionamentos, serviços e impactos; CMDB não se confunde com ITAM.",
    "monitoring_event": "Integrações com Zabbix e outras fontes para eventos, correlação e geração de incidentes.",
    "knowledge": "Artigos, busca, base de conhecimento e gestão de versões.",
    "measurement_reporting": "Métricas configuráveis, relatórios gerenciais e indicadores de processo.",
    "continual_improvement": "Registro de iniciativas de melhoria, avaliação, priorização e medição de resultados.",
    "information_security": "Inventário de controles, tratamento de riscos e integração com fluxos de incidentes.",
    "service_desk": "Portal/central de atendimento, canais, filas, comunicação e experiência do usuário.",
}

def implementation_status(practice_key: str) -> str:
    if practice_key not in BY_KEY:
        raise KeyError(f"Prática desconhecida: {practice_key}")
    return "mvp" if practice_key in IMPLEMENTED_MVP else "planned"

def counts():
    delivered = sum(implementation_status(p.key) == "mvp" for p in PRACTICES)
    return {"total": len(PRACTICES), "mvp": delivered, "planned": len(PRACTICES) - delivered}

def summary(practice_key: str) -> dict:
    practice = BY_KEY[practice_key]
    status = implementation_status(practice_key)
    return {
        "key": practice.key, "name": practice.name, "portuguese": practice.portuguese,
        "group": practice.group, "status": status,
        "delivered": DELIVERED.get(practice_key, "Ainda não implementada nesta aplicação."),
        "roadmap": NEXT_STEPS.get(
            practice_key,
            "Prática registrada no roadmap; escopo e critérios de aceite a detalhar."
        ),
        "tab_index": MODULE_TABS.get(practice_key),
    }
