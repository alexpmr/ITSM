# Backlog — PT2VHF ITSM

## Objetivo e princípios
Implementar práticas ITIL de maneira operacional, sem alegar conformidade/acreditação.
A lista do pedido repetia "mudanças"; para a quinta prática foi incluída gestão de incidentes.
Windows x64 é a plataforma inicial. GitHub é a fonte oficial.

## v0.1.0 — MVP desktop local
- [x] Incidentes: abertura, triagem, atendimento, espera, resolução, reabertura e encerramento
- [x] Requisições: abertura, aprovação, atendimento e encerramento
- [x] Mudanças: avaliação, decisão de aprovação, janela, implementação, reversão, revisão
- [x] Problemas: investigação, erro conhecido, resolução e encerramento
- [x] Inventário de ativos: patrimônio, tipo, série, responsável, localização, situação
- [x] Relacionar registros a ativos e problemas
- [x] Histórico de operações com operador informado manualmente
- [x] Dashboard básico, filtros, CSV, backup SQLite
- [x] Build executável Windows x64 via GitHub Actions
- [x] Testes de fluxo e persistência
- [ ] Testes end-to-end de interface em runner Windows e assinatura de código

## Distribuição e atualização do aplicativo (OTA)
- [x] CI para Windows x64, com executável portátil e instalador publicados nas GitHub Releases.
- [x] Tabela da última versão e contadores de downloads cumulativos no README.
- [ ] **[OTA pelo GitHub Releases — issue #9](https://github.com/alexpmr/ITSM/issues/9):** verificar atualizações ao iniciar (opcional) e manualmente pelo menu Ajuda, comparar versões e mostrar notas.
- [ ] Download com progresso e cancelamento, seleção de Setup/portátil, SHA-256 verificável, confirmação de atualização, mecanismo externo para substituir EXE, preservação de SQLite e testes de falha/rollback.
- [ ] Atualizar o workflow de Releases para publicar e validar um manifesto de checksums consumido pelo OTA.

## v0.2 — operação e qualidade
- [x] SLA transversal MVP por prática/prioridade, metas de resposta/resolução, calendário 24x7/útil, feriados e pausas
- [x] Indicadores SLA no dashboard e nos módulos; mapa ITIL com sete práticas em MVP parcial
- [ ] SLA por serviço/oferta (depende do catálogo de serviços, issue #6)
- [ ] Acordos contratuais, OLAs, escalonamento e notificações pré-violação
- [x] Calendários úteis e relógios de pausa básicos; pendentes regras por serviço, escalonamento e notificações
- [ ] Incidentes maiores, matriz impacto x urgência e prioridades parametrizáveis
- [ ] Catálogo de serviços e requisições com modelos e formulários dinâmicos
- [ ] Mudanças: categorias normal/padrão/emergencial; CAB; plano de teste; PIR; conflito de janelas
- [ ] Problemas: causa-raiz, workaround, base de erros conhecidos (KEDB)
- [ ] Ativos: ciclo de vida, contratos, garantias, importação CSV, descoberta, reconciliacão
- [x] CMDB MVP independente do ITAM, cadastro de CIs, relações direcionais, criticidade e dependências
- [x] CIs associados M:N a incidentes, requisições, mudanças e problemas, com análise de impacto topológica
- [x] Referência opcional 1:1 de CI ao ativo, histórico local, migração SQLite v3 e acesso pelo menu ITIL
- [ ] CMDB corporativa: descoberta, reconciliação, baselines, governança, APIs e associação ao catálogo (#6)
- [ ] Anexos, comentários, tarefas, notificações e histórico mais detalhado
- [ ] Busca avançada, exportação de relatórios, dashboards por prática
- [ ] Localização PT-BR / EN / ES / FR

## v0.3 — camada corporativa
- [ ] Backend centralizado PostgreSQL + API REST e cliente Windows
- [ ] Autenticação OIDC/AD, RBAC por papéis, segregação de funções
- [ ] Aprovação eletrônica verificável, assinatura de decisões e trilha imutável
- [ ] Múltiplas equipes, filas, grupos e multiempresa
- [ ] Migrações de banco versionadas e testes de recuperação
- [ ] Criptografia de dados sensíveis, gestão de segredos, backup/restore central
- [ ] API, webhooks e integrações com e-mail, AD, Zabbix, inventário

## v0.4 — IA assistiva sob controle
- [ ] Consultas em linguagem natural a registros por interface controlada
- [ ] Classificação e resumo sugeridos com indicação de confiança e revisão humana
- [ ] Sugestão de duplicidades, vínculos de problemas e artigos de conhecimento
- [ ] Proteção contra prompt injection, isolamento de dados e auditoria do uso de IA
- [ ] Nunca permitir mudanças/aprovações autônomas sem autorização

## Critérios de aceite de uso corporativo
O MVP não possui identidade verificada, perfis, aprovação confiável ou SLA corporativo governado, mesmo com contagem de calendário no MVP.
Não utilizar como sistema de registro oficial de produção até concluir os controles
de segurança, privacidade, auditoria, recuperação e requisitos organizacionais.
