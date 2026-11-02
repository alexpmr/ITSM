# PT2VHF ITSM

**MVP 0.3.0 (em evolução)** — aplicação desktop de gestão de serviços de TI, com interface Windows,
persistência local SQLite e práticas inspiradas em ITIL.

## Escopo inicial

| Prática | O que já existe |
| --- | --- |
| Gerenciamento de incidentes | Registro, priorização manual, triagem, atendimento, resolução, reabertura |
| Gerenciamento de requisições de serviço | Registro, aprovação declaratória, atendimento, encerramento |
| Habilitação de mudanças | Avaliação, aprovação, janela planejada, implementação, rollback, revisão |
| Gerenciamento de problemas | Investigação, erro conhecido, resolução, relacionamento com registros |
| Gerenciamento de ativos de TI | Cadastro, responsável, localização, identificação, estado, vínculos |
| Gestão de níveis de serviço | Políticas de SLA por prática e prioridade, metas de resposta/resolução, dias úteis, feriados, estados de pausa, indicadores |
| Gestão da configuração de serviços (CMDB) | Cadastro de CIs, relações direcionais, impacto potencial, vínculo M:N com incidentes, requisições, mudanças e problemas, referência opcional ao ITAM |

O sistema inclui dashboard, pesquisa, histórico de ações, exportação CSV e backup SQLite.
O menu superior **ITIL** abre mapa das 34 práticas, realçando as sete com módulo MVP parcial, e oferece navegação e exportação do roadmap.

**Importante:** o pedido original citava "mudanças" duas vezes. A quinta prática foi
interpretada como **gerenciamento de incidentes**, que complementa o ciclo operacional.

## Requisitos

- Windows 10/11 x64 (alvo de build; validação de compatibilidade pendente).
- Para executar do código: Python 3.12 e PySide6.
- Não requer servidor ou internet para operar.

## Execução a partir dos fontes

No PowerShell, na pasta do repositório:

    py -3.12 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    .\.venv\Scripts\python.exe main.py

Abra a aba **SLA**, cadastre uma política (código, prática, prioridade, metas e calendário), salve e crie um registro operacional. A política mais específica ativa compatível será atribuída automaticamente. O indicador de SLA aparece na lista de cada prática e no painel inicial. Pode atribuir manualmente outra política compatível ao editar o registro.

**Importante:** os valores iniciais exibidos no formulário de SLA são apenas sugestões de preenchimento, não acordos reais. Valide metas com cada área demandante.

O banco é criado em:

    %LOCALAPPDATA%\PT2VHF\ITSM\itsm.db

A pasta de trabalho não deve conter um arquivo de banco no Git.

## Gerar executável Windows

    powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1

O comando verifica os testes e empacota em:

    dist\PT2VHF-ITSM.exe

Também há um pipeline GitHub Actions em **Actions > CI e build Windows**.
Quando o workflow completar com sucesso, o EXE poderá ser obtido no artefato
**PT2VHF-ITSM-Windows-x64** da execução. O executável é portátil, não é
um instalador MSI e ainda não é assinado digitalmente.

## Testes

    .\.venv\Scripts\python.exe -m pytest -q

## Funcionalidades importantes

- IDs automáticos INC-000001, REQ-000002, CHG-000003 e PRB-000004
  (numeração global; cada prefixo identifica a prática).
- Transições de status validadas na camada de dados, não apenas na interface.
- Requisições aguardando aprovação exigem decisão específica.
- Mudanças precisam de aprovação antes do agendamento e planos de
  implementação e reversão antes da implementação.
- Não é possível vincular um registro a um problema inexistente ou a si próprio.
- Auditoria local de criação, atualização, transição e decisão, com data UTC.

## Limitações e segurança

**Esta é uma versão inicial para demonstração e desenvolvimento, não uma solução
pronta para operação corporativa de missão crítica.**

- Uso local, monousuário, banco não criptografado.
- Nome do operador é informado livremente na tela; não há autenticação,
  segregação de funções, RBAC nem aprovação eletrônica com identidade validada.
- A trilha de auditoria pode ser alterada por quem controla o arquivo SQLite.
- Prioridade, prazo e risco são informados manualmente; não existe SLA
  com calendário útil, automação de escalonamento ou motor de regras.
- Há CMDB funcional em escopo MVP, mas sem descoberta automática, reconciliação, baselines, catálogo de serviços, anexos ou integrações.
- Banco SQLite usa migrações incrementais v1 → v2 (SLA) → v3 (CMDB), idempotentes; preserve backup antes de atualizar.
- O módulo de SLA contabiliza metas, não substitui definição contratual formal nem automação de alertas.
- Políticas podem ser aplicadas automaticamente a novos registros de incidentes, requisições, mudanças e problemas.
- Não há vínculo SLA por serviço porque o catálogo transversal permanece no backlog; por enquanto a seleção usa tipo e prioridade.
- O relógio contabiliza minutos em calendários 24x7 ou comerciais, com fuso America/Sao_Paulo e feriados configurados por política.
- Mudanças nos modelos de SLA não alteram registros já vinculados (snapshot).

Utilize **Arquivo > Fazer backup do banco** para criar cópia consistente e
**Arquivo > Exportar aba para CSV** para extrações simples.

O [backlog de evolução](docs/BACKLOG.md) separa as funcionalidades demonstráveis
dos requisitos indispensáveis a uma implementação corporativa.

## Licenciamento e metodologia

ITIL é marca de seus respectivos titulares. Este projeto não é afiliado,
certificado nem acreditado pela PeopleCert. Não distribui material proprietário
das publicações ITIL.

Projeto PT2VHF. Contribuições via issues e pull requests.


## CMDB transversal (MVP 0.3)

A aba **CMDB** administra itens de configuração (CIs) independentes de ativos patrimoniais.

1. Cadastre CIs com código único, classe, ambiente, criticidade, situação, responsável e associação opcional com um ativo ITAM.
2. Use **Relacionar CIs** para informar dependências direcionais: depends_on, hosted_on, supports e connects_to. Dependências circulares e auto-relacionamentos não são aceitos.
3. Nos formulários de incidentes, requisições, problemas ou mudanças, use **Selecionar CIs** para relacionar múltiplos itens e seus papéis (affected, target, related).
4. Use **Analisar impacto** sobre um CI para visualizar os CIs dependentes e os registros ITSM associados. A análise é topológica, não certifica indisponibilidade real; conexões genéricas não propagam impacto.
5. A aba ITIL sinaliza *Service configuration management* como **MVP parcial**, totalizando sete práticas implementadas parcialmente.

A CMDB mantém chaves estrangeiras e trilha de mudanças local. ITAM continua separado, com vínculo 1:1 opcional no MVP. O nome de serviço é provisoriamente texto livre; o catálogo de serviços transversal (#6) ainda não está pronto. A aplicação não descobre automaticamente configurações, não integra sistemas externos e não dispõe de controle de acesso corporativo.

É recomendado criar backup antes de atualizar a aplicação.
