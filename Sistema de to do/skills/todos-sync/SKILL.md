---
name: todos-sync
description: |
  Pipeline A de fallback para sincronizar to-dos a partir de transcrições. Quando auto_sync.py
  estiver instalado, prefira executá-lo: ele consulta Calendar/Drive, usa Gemini, deduplica,
  registra observabilidade e regenera o dashboard sem depender de uma sessão do Claude.
trigger:
  manual: /todos-sync
mcps_required:
  - Google Drive
  - Google Calendar
state_files:
  - People/{Nome}/.todos/last-sync.json
  - People/{Nome}/.todos/refresh-trigger.json
  - People/{Nome}/.todos/meeting-sync-log.json
  - People/{Nome}/.todos/change-log.jsonl
---

# /todos-sync — Pipeline A (genérico)

## Preferência

Se `{BASE}/auto_sync.py` existir, executar:

```bash
python3 "{BASE}/auto_sync.py" --from "{from}" --to "{to}" --max-files 0
```

Continue com o fluxo abaixo apenas quando o Python automático não estiver disponível.

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

Inicializar um acumulador de observabilidade da execução:

```json
{
  "schema_version": "1.0",
  "last_run_at": "{ISO America/Sao_Paulo}",
  "range": {
    "from": "{from}",
    "to": "{to}",
    "preset": "{preset}",
    "force_reprocess": false
  },
  "summary": {
    "events_total": 0,
    "events_processed": 0,
    "events_skipped": 0,
    "transcripts_found": 0,
    "transcripts_missing": 0,
    "todos_created": 0,
    "todos_updated": 0,
    "todos_review_needed": 0
  },
  "events": []
}
```

Estados permitidos por evento:

- `status`: `processed`, `skipped`, `error`
- `transcript_status`: `found`, `missing`, `not_required`, `unknown`
- `reason`: `no_meet_link`, `no_conference_record`, `no_transcript`, `already_processed`, `no_action_items`, `no_clear_owner_assignment`, `outside_scope`, `error`

Regra central: **todo evento do range deve aparecer em `meeting-sync-log.json`**, mesmo quando não houver task.

---

## PASSO 2 — Listar transcrições no Drive (range)

Usar MCP Google Drive conforme disponível no ambiente.

**Regra:** processar **um arquivo por vez**; salvar `todos-data.json` após cada um.

Se MCP Google Calendar estiver disponível, listar também os eventos do calendário no range e pré-registrar cada evento no acumulador com:

- `event_id`
- `title`
- `started_at`
- `ended_at`
- `meeting_code`, se houver
- `status: "skipped"`
- `transcript_status: "unknown"`
- `reason: null`

Filtrar por data do nome/arquivo dentro de `from` → `to`.

Respeitar `processed_file_ids[]` salvo em `last-sync.json` (pular se já processado, exceto `force_reprocess: true`).

Quando uma transcrição for encontrada, associar ao evento por `meeting_code`, título/data ou fallback por proximidade. Se não existir evento correspondente, criar uma entrada sintética usando o arquivo da transcrição como origem.

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

Após cada arquivo/evento analisado, atualizar a entrada correspondente em `meeting-sync-log.json` no acumulador:

- Se processou com transcrição: `status: "processed"`, `transcript_status: "found"`, `reason: null`
- Se estava em `processed_file_ids[]` e `force_reprocess == false`: `status: "skipped"`, `reason: "already_processed"`
- Se não achou transcrição: `status: "skipped"`, `transcript_status: "missing"`, `reason: "no_transcript"`
- Se não havia link Meet: `status: "skipped"`, `transcript_status: "missing"`, `reason: "no_meet_link"`
- Se não houve ação extraível: `status: "skipped"`, `reason: "no_action_items"`
- Se a ação era de outra pessoa e não do owner/grupo aplicável: `status: "skipped"`, `reason: "no_clear_owner_assignment"` ou `outside_scope`
- Se ocorreu falha: `status: "error"`, `reason: "error"`, com `notes` explicando o erro

Campos mínimos por evento:

```json
{
  "event_id": "calendar-or-drive-id",
  "title": "Nome da reunião",
  "started_at": "2026-06-04T09:00:00-03:00",
  "ended_at": "2026-06-04T09:30:00-03:00",
  "meeting_code": "abc-defg-hij",
  "status": "processed",
  "transcript_status": "found",
  "transcript_source": "Google Drive",
  "transcript_path": "{BASE}/.todos/transcripts/arquivo.md",
  "todos_created": 3,
  "todos_updated": 0,
  "todos_review_needed": 1,
  "reason": null,
  "notes": "Processado com fala/assunção clara do owner."
}
```

---

## PASSO 4 — Agenda D+1

Se `calendar.enabled`:
- Sexta → segunda; demais dias → D+1
- Inserir em `sprints[current].agenda_tomorrow` se campo existir no schema

---

## PASSO 5 — Persistir

- Write `{DATA}`
- Update `last-sync.json`
- Write `{STATE}/meeting-sync-log.json` com o acumulador final
- Append `change-log.jsonl`

Antes de escrever `meeting-sync-log.json`, recalcular o `summary` a partir de `events[]`:

- `events_total`: total de eventos registrados
- `events_processed`: eventos com `status == "processed"`
- `events_skipped`: eventos com `status == "skipped"`
- `transcripts_found`: eventos com `transcript_status == "found"`
- `transcripts_missing`: eventos com `transcript_status == "missing"`
- `todos_created`: soma de `todos_created`
- `todos_updated`: soma de `todos_updated`
- `todos_review_needed`: soma de `todos_review_needed`

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
  Eventos analisados: {events_total}
  Com transcrição: {transcripts_found}
  Sem transcrição: {transcripts_missing}
  Sem tarefa clara: {N no_clear_owner_assignment + no_action_items}
```

---

## Impedimentos

- Auth Drive expirada → **PAUSAR**, pedir reconexão
- Arquivo vazio → pausar e perguntar
- Nunca skip silencioso
