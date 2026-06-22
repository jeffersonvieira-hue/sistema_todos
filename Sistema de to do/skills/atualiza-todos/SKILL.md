---
name: atualiza-todos
description: |
  Atualiza o sistema de to-dos pelo pipeline Python local, usando Calendar, Drive e Gemini,
  com deduplicação, observabilidade e regeneração automática do dashboard. Use quando o
  usuário pedir para atualizar to-dos ou executar um range manual.
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

## Caminho preferencial — Python automático

Se `People/{Nome}/auto_sync.py` existir, ele é a fonte principal do Pipeline A.

Range explícito:

```bash
python3 "People/{Nome}/auto_sync.py" \
  --from "YYYY-MM-DD" \
  --to "YYYY-MM-DD" \
  --max-files 0
```

Sem range explícito, o script lê `.todos/refresh-trigger.json`; sem trigger, usa os últimos dois dias:

```bash
python3 "People/{Nome}/auto_sync.py" --lookback-days 2 --max-files 5
```

Use `--force` somente quando solicitado. O script protege tasks concluídas, mescla duplicatas,
grava `meeting-sync-log.json` e regenera o dashboard.

Se `auto_sync.py` não existir, usar a skill **todos-sync** como fallback.

---

## Passo 2 — Pipeline B (se aplicável)

Se `user-config.cockpit.enabled == true`:

Executar **todos-project-alerts** (skill em `releases/` ou versão futura no repo).

Usar `cockpit.project_document_ids` do user-config.

Se Cockpit desabilitado: pular com nota no report.

---

## Passo 3 — Report consolidado

Ler `People/{Nome}/.todos/meeting-sync-log.json` após o Pipeline A e incluir o resumo da última atualização no report.

```
[/atualiza-todos] ✅ — {timestamp}

Pipeline A:
  Período: {from} → {to}
  Arquivos: {N} | Novos items: {N} | Atualizados: {N}
  Eventos analisados: {events_total}
  Com transcrição: {transcripts_found}
  Sem transcrição: {transcripts_missing}
  Sem tarefa clara: {no_action_items + no_clear_owner_assignment}

Pipeline B:
  {habilitado|desabilitado} | Alertas: {N}

Dashboard: People/{Nome}/todos-dashboard.html
```

Separar no report:

- novas no dashboard;
- enfileiradas para Ekyte;
- criadas no Ekyte.

---

## Instalação inicial

Se `install-state.mapping_status == pending`:
1. Avisar: rodar `/todos-installer` Fase B antes
2. Ou executar Fase B inline se MCP disponível
