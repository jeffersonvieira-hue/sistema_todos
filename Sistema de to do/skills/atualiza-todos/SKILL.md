---
name: atualiza-todos
description: |
  Orquestrador: Pipeline A (/todos-sync) + Pipeline B (/todos-project-alerts) se Cockpit
  habilitado. Paths dinâmicos via user-config.json.
trigger:
  manual: /atualiza-todos
---

# /atualiza-todos — Orquestrador

## Resolver usuário

Identificar `People/{Nome}/` pelo contexto da conversa ou perguntar.

```
Read: People/{Nome}/.todos/user-config.json
```

---

## Passo 0 — Trigger do dashboard

```
Read: People/{Nome}/.todos/refresh-trigger.json
```

Se existir, mostrar período no report e passar parâmetros ao `/todos-sync`.

---

## Passo 1 — Pipeline A

Executar **todos-sync** completo (inclui **todos-dedup** ao final).

---

## Passo 2 — Pipeline B (se aplicável)

Se `user-config.cockpit.enabled == true`:

Executar **todos-project-alerts** (skill em `releases/` ou versão futura no repo).

Usar `cockpit.project_document_ids` do user-config.

Se Cockpit desabilitado: pular com nota no report.

---

## Passo 3 — Report consolidado

```
[/atualiza-todos] ✅ — {timestamp}

Pipeline A:
  Período: {from} → {to}
  Arquivos: {N} | Novos items: {N}

Pipeline B:
  {habilitado|desabilitado} | Alertas: {N}

Dashboard: People/{Nome}/todos-dashboard.html
```

---

## Instalação inicial

Se `install-state.mapping_status == pending`:
1. Avisar: rodar `/todos-installer` Fase B antes
2. Ou executar Fase B inline se MCP disponível
