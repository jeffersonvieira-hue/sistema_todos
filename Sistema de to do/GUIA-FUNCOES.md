# Guia de Funções — Captura de Tasks por Perfil

O sistema extrai tasks de forma diferente dependendo da função configurada em `user-config.json`.

---

## Como o sistema decide o que capturar

Para cada transcrição de reunião, o sistema aplica duas regras:

1. **Owner explícito** — você é mencionado pelo nome como responsável
2. **Grupo da função** — a tarefa é para "todos os coordenadores", "equipe de tráfego", etc.

Além disso, cada função tem regras adicionais de acompanhamento.

---

## Coordenador

**Categorias:** Alertas, Financeiro, Projetos, Processos, Equipe, Recorrentes

**O que captura:**
- Tasks com seu nome como owner explícito
- Tasks direcionadas a "todos os coordenadores" ou "coordenação"
- Acompanhamentos críticos de projetos da carteira
- Alertas automáticos de projetos com score Critical/Danger (via Cockpit)

**Reuniões relevantes:**
- Daily da BU
- Daily Coordenação/Gerência
- 1a1 com duplas
- Quality Check
- Comitê Ops
- Reuniões de Monetização

**O que ignora:**
- Tasks de outros coordenadores sem follow-up necessário
- Comentários gerais de equipe sem ação definida para você

---

## Gestor de Projetos

**Categorias:** Clientes, Entregas, Alinhamentos, Dependências, Riscos, Recorrentes

**O que captura:**
- Pendências com cliente (aprovação, feedback, reunião)
- Follow-ups internos com prazo
- Impedimentos que bloqueiam entregas
- Handoffs e passagens de bastão
- Aprovações pendentes de materiais

**O que ignora:**
- Execução operacional de tráfego/criativo (sem seu envolvimento direto)

---

## Gestor de Tráfego

**Categorias:** Campanhas, Tracking, Criativos, Investimento, Relatórios, Recorrentes

**O que captura:**
- Ajustes de campanha com prazo
- Configurações de pixel, API de conversão, tracking
- Análises de performance solicitadas
- Solicitações de criativos e materiais
- Pendências de orçamento e investimento

**O que ignora:**
- Tarefas de copy e design sem relação com tráfego

---

## Copywriter

**Categorias:** Briefings, Copys, Roteiros, Revisões, Pesquisa, Recorrentes

**O que captura:**
- Demandas de copy com prazo e cliente especificado
- Ajustes de tom, voz e mensagem
- Roteiros de vídeo e reels
- Headlines e promessas de oferta
- Pesquisa de concorrentes e referências

**O que ignora:**
- Execução de tráfego, design ou CRM sem copy envolvida

---

## Designer

**Categorias:** Criativos, Landing Pages, Identidade Visual, Revisões, Referências, Recorrentes

**O que captura:**
- Peças solicitadas com briefing e prazo
- Revisões com feedback específico
- Materiais de identidade visual
- Referências de design aprovadas para produção

**O que ignora:**
- Tasks sem briefing de design claro

---

## Social Media

**Categorias:** Conteúdo, Calendário Editorial, Publicações, Comunidade, Relatórios, Recorrentes

**O que captura:**
- Posts e reels com data de publicação
- Aprovações de pauta e calendário
- Interações críticas de comunidade
- Relatórios de performance de conteúdo

---

## BI / Dados

**Categorias:** Dashboards, Tracking, Bases, Relatórios, Automações, Recorrentes

**O que captura:**
- Dashboards a criar ou atualizar
- Eventos e tags a implementar
- Queries e integrações pendentes
- Validações de dados solicitadas

---

## Atendimento / CRM

**Categorias:** Leads, CRM, Atendimento, Follow-up, Automações, Recorrentes

**O que captura:**
- Ajustes de fluxo CRM com prazo
- Qualificação de leads pendente
- Follow-ups comerciais agendados
- Configurações de automação de atendimento

---

## Personalizar a captura

Para ajustar as regras de extração da sua função, edite:

```
People/{Seu Nome}/.todos/user-config.json
```

Campo `extraction.role_rules` — liste regras adicionais em português.

Exemplo:
```json
"role_rules": [
  "Capturar tasks de API de conversão para projetos de e-commerce",
  "Capturar alertas de queda de leads do Google"
]
```
