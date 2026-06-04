---
name: todos-sync
description: |
  Pipeline A — Sincroniza to-dos do usuário a partir de transcrições no Google Drive.
  Paths dinâmicos via user-config.json. Ao final, invoca todos-dedup automaticamente.
trigger:
  manual: /todos-sync
mcps_required:
  - Google Drive
  - Google Calendar
state_files:
  - People/{Nome}/.todos/last-sync.json
  - People/{Nome}/.todos/refresh-trigger.json
  - People/{Nome}/.todos/change-log.jsonl
---

# /todos-sync — Pipeline A (genérico)

## Setup — resolver paths

```
Read: People/{Nome}/.todos/user-config.json
```

Derivar:
- `BASE = user.paths.base_dir` (ex: `People/Ana Souza`)
- `DATA = {BASE}/todos-data.json`
- `STATE = {BASE}/.todos/`
- `OWNER = user.full_name`, `EMAIL = user.email`
- `OWNER_NAMES = extraction.owner_names`
- `ROLE_RULES = extraction.role_rules`

Prompt de extração: preencher `Sistema de to do/templates/prompts/extract-todos.template.md` com dados do `user-config.json`.

---

## PASSO 0 — Trigger de range

```
Read: {BASE}/.todos/refresh-trigger.json
```

Se existir: usar `from`, `to`, `force_reprocess`, `preset`. **Apagar** arquivo ao concluir.

Se não existir (cron):
```
from = to = hoje (America/Sao_Paulo)
force_reprocess = false
```

---

## PASSO 1 — Estado

```
Read: {BASE}/.todos/last-sync.json
Read: {DATA}
```

---

## PASSO 2 — Listar transcrições no Drive (range)

Usar MCP Google Drive conforme disponível no ambiente.

**Regra:** processar **um arquivo por vez**; salvar `todos-data.json` após cada um.

Filtrar por data do nome/arquivo dentro de `from` → `to`.

Respeitar `processed_file_ids[]` salvo em `last-sync.json` (pular se já processado, exceto `force_reprocess: true`).

---

## PASSO 3 — Extração (por arquivo)

Para cada transcrição:

1. **Pass 1** — itens estruturados (tabela/checklist na nota)
2. **Pass 2** — compromissos verbais do owner (`OWNER_NAMES`)

Regras em `user-config.extraction`:
- `capture_direct_assignments`, `capture_follow_ups`, `ignore_other_people_tasks`
- `role_rules` da função

Cada item:
```json
{
  "id": "{sprint}-{slug}-{hash}",
  "title": "...",
  "context": "...",
  "priority": "normal|urgente|recorrente",
  "done": false,
  "source": "{nome reunião}",
  "confidence": "alta|média",
  "review_needed": false
}
```

**Dedup inline** (antes de append): similaridade título > 0.85 com item existente → não duplicar; enriquecer `context` se relevante. **Nunca** alterar items `source` contendo `Manual`.

---

## PASSO 4 — Agenda D+1

Se `calendar.enabled`:
- Sexta → segunda; demais dias → D+1
- Inserir em `sprints[current].agenda_tomorrow` se campo existir no schema

---

## PASSO 5 — Persistir

- Write `{DATA}`
- Update `last-sync.json`
- Append `change-log.jsonl`

---

## PASSO 6 — Dedup global (obrigatório)

Executar skill **todos-dedup** (sub-rotina).

---

## PASSO 7 — Regenerar dashboard

```bash
python3 "{BASE}/generate_dashboard.py"
```

---

## Report

```
[/todos-sync] ✅ Período {from}→{to}
  Processados: {N} arquivos
  Adicionados: {N} items
  Dedup inline: {N}
  Dedup global: ver todos-dedup
```

---

## Impedimentos

- Auth Drive expirada → **PAUSAR**, pedir reconexão
- Arquivo vazio → pausar e perguntar
- Nunca skip silencioso
