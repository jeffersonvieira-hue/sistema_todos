---
name: todos-installer
description: |
  Instala e configura o Sistema de To-Dos Operacionais V2: estrutura local (Python) +
  mapeamento Ekyte/Cockpit via MCP + primeiro sync. Use na instalação de novo player
  ou quando mapping_status != complete.
trigger:
  manual: /todos-installer
mcps_required:
  - ekyte
  - cockpit
  - Google Drive (sync)
  - Google Calendar (sync)
output_files:
  - People/{Nome}/.todos/mapeamento.md
  - People/{Nome}/.todos/ekyte-config.json
  - People/{Nome}/.todos/user-config.json
  - People/{Nome}/.todos/install-state.json
  - People/{Nome}/.todos/refresh-trigger.json
---

# /todos-installer — Instalação completa (2 fases)

## Quando usar

- Primeiro player instalando o sistema
- `install-state.json` com `mapping_status: pending`
- `ekyte-config.json` com `workspaces: []`
- Reinstalação pedindo atualização de mapeamento

---

## Fase A — Estrutura (Python)

Rodar no repo:

```bash
python3 "Sistema de to do/install_todos.py" \
  --name "{Nome}" \
  --email "{email}" \
  --role "{role}" \
  --bu "{bu}" \
  --squad "{squad}" \
  --sync-preset last7 \
  --yes
```

Isso cria `People/{Nome}/`, `refresh-trigger.json`, `mapeamento.md` (esqueleto) e dashboard vazio.

**Exit code 2** = estrutura OK, mapeamento pendente → continuar Fase B.

---

## Fase B — Validação e mapeamento (MCP)

### B0 — Carregar contexto

```
Read: People/{Nome}/.todos/user-config.json
Read: People/{Nome}/.todos/ekyte-config.json
Read: People/{Nome}/.todos/install-state.json
Read: People/{Nome}/.todos/refresh-trigger.json
Read: People/{Nome}/.todos/mapeamento.md
```

Se `mapping_status == complete` e usuário não pediu refresh: validar apenas e reportar OK.

### B1 — Perguntas (se necessário)

1. Confirmar BU/Squad (`user.bu`, `user.squad`)
2. Workspace Ekyte padrão (lista numerada após busca MCP)
3. Trimestre vigente para filtrar projetos (ex: Q2/2026)
4. Confirmar range do primeiro sync (`refresh-trigger.json`)

### B2 — MCP Ekyte

| Tool | Parâmetros | Objetivo |
|---|---|---|
| `list_short_workspaces` | `textSearch`: BU/squad, `active`: 1 | Workspaces |
| `list_projects` | `workspaceId`, `active`: 1 | Projetos por workspace |
| `list_task_types` | workflow Colli | Tipos de task |
| `list_tags` | — | IDs de routine/week tags |

Para cada workspace selecionado, popular em `ekyte-config.json`:

```json
{
  "id": "112225",
  "name": "[Invictus] ...",
  "projects": [{"id": "216299", "name": "..."}],
  "task_types": [{"id": "68301", "name": "..."}]
}
```

**Sempre append** sentinelas `__other__` em workspaces, projects, task_types e assignees (ver template).

Definir: `default_workspace_id`, `default_task_type_id`, `default_assignee_email`.

### B3 — MCP Cockpit (time + projetos)

Fonte principal de **pessoas do time**.

```
cockpit_query_table
  filterByUser: documentId do coordenador (se conhecido)
  filters: BU/squad conforme user-config
```

Extrair por projeto:
- `documentId` → `user-config.cockpit.project_document_ids`
- `ticker` → `user-config.cockpit.ticker_filter`
- Coordenador / GT / e-mails → `ekyte-config.assignees`

Incluir o próprio usuário instalado. Append `{ "id": "__other__", "name": "Outros (informar e-mail)", "is_other": true }`.

### B4 — Gerar mapeamento.md

Reescrever `People/{Nome}/.todos/mapeamento.md` com tabelas preenchidas:
- Workspaces / Projetos / Tipos / Tags
- Projetos Cockpit
- Time Cockpit
- Pendências manuais (Outros)

### B5 — Persistir estado

```json
// install-state.json
{
  "mapping_status": "complete",
  "mapped_at": "{ISO}",
  "bu": "...",
  "squad": "..."
}
```

---

## Fase C — Automação local

Ativar servidor contínuo e sincronização a cada duas horas, somente de segunda a sexta:

```bash
python3 "Sistema de to do/install_automation.py" --name "{Nome}"
```

Isso cria uma cópia operacional em `~/Library/Application Support/Todos {PrimeiroNome}/`,
instala dois LaunchAgents e mantém tokens fora do Git.

Antes do primeiro sync:

1. Salvar `GEMINI_API_KEY` em `~/.config/todos-auto-sync/secrets.env`.
2. Confirmar credenciais OAuth em `~/.claude/gdrive/credentials.json`.
3. Rodar `People/{Nome}/setup_google_oauth.py`.
4. Validar com `People/{Nome}/auto_sync.py --check`.

---

## Fase D — Primeiro sync + dedup

1. Executar `auto_sync.py` (usa `refresh-trigger.json`)
2. Confirmar `meeting-sync-log.json`
3. Regenerar dashboard, caso necessário:

```bash
python3 "People/{Nome}/generate_dashboard.py"
```

4. Abrir `http://127.0.0.1:8787/` e confirmar items > 0

---

## Opção "Outros"

Se ID não aparecer no MCP:
1. Registrar em `mapeamento.md` → Pendências manuais
2. Manter sentinel `__other__` no JSON
3. Usuário preenche ID no modal Ekyte do dashboard

---

## Diagnóstico

| Sintoma | Ação |
|---|---|
| workspaces vazio | Rodar Fase B |
| Cockpit sem projetos | Verificar token + filtro BU |
| Dashboard vazio após install | Rodar Fase C (`/atualiza-todos`) |
| Exit code 2 do Python | Normal na 1ª vez — continuar Fase B |
| Botão Atualizar não executa | Abrir pelo servidor `127.0.0.1:8787`, não por `file://` |
| Sync automático não roda | Conferir LaunchAgent e logs em `.todos/auto-sync-launchd*.log` |
