# Arquitetura do Sistema

## Objetivo

Todo fim de dia, o sistema deve olhar a agenda do Jefferson, abrir as transcrições das calls no Google Drive, extrair os compromissos relevantes e deixar o dashboard pronto para a manhã seguinte.

O resultado esperado é uma lista curta o bastante para ser acionável, mas completa o bastante para não deixar follow-ups importantes escaparem.

## Componentes

### 1. Fonte de verdade

`People/Jefferson Vieira/todos-data.json`

Contém:

- `meta`: versão, sprint atual, owner, schema.
- `sprints`: sprint atual e histórico.
- categorias da sprint atual:
  - `alertas`
  - `financeiro`
  - `projetos`
  - `processos`
  - `equipe`
  - `recorrentes`
- itens com campos como `id`, `title`, `context`, `priority`, `source`, `confidence`, `review_needed`, `source_timestamp`, `source_quote`.

### 2. Gerador e servidor

`People/Jefferson Vieira/generate_dashboard.py`

Responsabilidades:

- validar `todos-data.json`;
- gerar `todos-dashboard.html`;
- servir dashboard em `http://127.0.0.1:8787/`;
- expor endpoints locais:
  - `POST /api/refresh`
  - `POST /api/manual-task`
  - `POST /api/ekyte-queue`
  - `POST /api/regenerate`
  - `POST /write-json` restrito a `.todos/ekyte-pending.json`
- criar `.todos/refresh-trigger.json`;
- criar `.todos/ekyte-pending.json`;
- resetar sprint atual com backup em `.todos/archive/`;
- rodar em `--watch`.

### 3. Dashboard

`People/Jefferson Vieira/todos-dashboard.html`

É HTML self-contained com `DATA` embutido.

Funcionalidades atuais:

- filtros por status/categoria;
- busca inline;
- contador e barra de progresso;
- checkboxes persistidos no `localStorage`;
- painel de estado do sistema;
- botão **Adicionar task** para criar item manual na sprint atual;
- botão **Atualizar**;
- botão **↑ Ekyte** por item elegível.

O estado de checkbox no dashboard é local do navegador. O source of truth de to-dos continua sendo o JSON.

### 4. Helper Calendar + Drive

`People/Jefferson Vieira/todos_probe_one_event.py`

Responsabilidades:

- ler eventos do Google Calendar;
- localizar documentos do Google Drive com `Anotações do Gemini`;
- baixar transcrições para `.todos/transcripts/`;
- gerar `.todos/manifest-YYYY-MM-DD.json`;
- permitir teste por um evento ou baixar tudo com `--all`.

Caminhos de credenciais usados pelo script:

| Caminho | Uso |
| --- | --- |
| `/Users/jeffersonvieira/.config/google-calendar-mcp/tokens.json` | Token do Calendar. |
| `/Users/jeffersonvieira/.gdrive-server-credentials.json` | Token do Drive. |
| `/Users/jeffersonvieira/.claude/gdrive/credentials.json` | OAuth client. |

Nao versionar nem imprimir tokens.

### 5. Estado local

Diretório:

`People/Jefferson Vieira/.todos/`

Arquivos importantes:

| Arquivo | Uso |
| --- | --- |
| `last-sync.json` | Dedup e estatísticas do Pipeline A. |
| `last-alerts.json` | Dedup e estado do Pipeline B. |
| `change-log.jsonl` | Log append-only das execuções. |
| `refresh-trigger.json` | Criado pelo botão Atualizar no servidor local. |
| `ekyte-pending.json` | Criado pelo botão Ekyte no servidor local. |
| `refresh-errors.json` | Erros exibidos no dashboard, quando existirem. |
| `manifest-YYYY-MM-DD.json` | Relação de eventos/transcrições baixadas. |
| `transcripts/` | Texto exportado das anotações/transcrições Gemini. |
| `archive/` | Backups de reset/rotação. |

## Pipeline A: agenda e reuniões

Origem histórica no Claude:

- `~/.claude/skills/todos-sync/SKILL.md`
- `~/.claude/skills/todos-sync/prompts/extract-jefferson-todos.md`

Fluxo desejado:

1. Buscar eventos do dia anterior no Google Calendar.
2. Encontrar anotações/transcrições do Gemini no Google Drive.
3. Processar um evento por vez para não estourar contexto.
4. Fazer extração em duas passadas:
   - seção "Próximas etapas" do Gemini;
   - varredura da transcrição completa.
5. Adicionar itens no `todos-data.json`.
6. Atualizar `last-sync.json`.
7. Registrar `change-log.jsonl`.
8. Regenerar dashboard.

Critério de extração:

- compromisso verbal assumido por Jefferson;
- follow-up que Jefferson precisa cobrar;
- decisão que exige validação posterior;
- risco operacional que precisa acompanhamento;
- tarefa de terceiro quando Jefferson precisa garantir execução.

Exceção de reuniões de coordenação/gerência: em `Comitê Ops - Gerência Invictus` e `[Daily] - Coordenação/Gerência`, a extração deve descartar tarefas de outros coordenadores. Só entram itens do Jefferson, itens atribuídos a todos os coordenadores/coordenação/gerência, ou acompanhamentos em que Jefferson precise cobrar/garantir execução como coordenador da BU Invictus.

Use `review_needed: true` para itens de acompanhamento, autoria indireta ou baixa confiança.

## Pipeline B: alertas de projetos

Origem histórica no Claude:

- `~/.claude/skills/todos-project-alerts/SKILL.md`
- `~/.claude/skills/todos-project-alerts/lib/cockpit-signals.md`

Fluxo desejado:

1. Consultar Cockpit via MCP.
2. Avaliar os projetos da carteira.
3. Detectar sinais de risco:
   - Health Score crítico;
   - flag Critical/Danger;
   - ausência de check-in;
   - sem backlog;
   - antecipação ativa;
   - sinais comerciais ou operacionais.
4. Criar alertas na categoria `alertas`.
5. Atualizar `last-alerts.json`.
6. Regenerar dashboard.

## Atualizar pelo dashboard

O botão **Atualizar** faz uma coisa específica:

```text
POST /api/refresh
  -> grava .todos/refresh-trigger.json
  -> regenera o dashboard
```

Isso confirma a intenção de atualizar, mas ainda não executa sozinho todo o Pipeline A/B.

Estado atual:

- Com servidor local: botão grava o trigger corretamente.
- Sem servidor local: botão copia o comando como fallback.
- Falta implementar um consumidor automático de `refresh-trigger.json` que rode Calendar + Drive + extração + alertas.

## Ekyte

O botão **↑ Ekyte** aparece quando o item:

- é `priority: urgente`;
- tem `confidence: alta`;
- não tem `review_needed`;
- ainda não tem `ekaite_task_id`.
- não está em `SYSTEM_STATE.ekyte_pending[].item_id`.

Com servidor local, o botão grava `.todos/ekyte-pending.json`.

Sem servidor local, o botão:

1. tenta ler `.todos/ekyte-pending.json` por `fetch` relativo;
2. se não conseguir, usa `SYSTEM_STATE.ekyte_pending` embutido no HTML;
3. adiciona o item à fila;
4. tenta `POST /write-json`;
5. se não houver servidor, baixa `ekyte-pending.json` atualizado;
6. copia o JSON para a área de transferência.

O header mostra **Processar fila Ekyte (N)** quando há itens na fila embutida ou adicionada no cliente. O clique copia:

```text
/todos-promote-ekaite
```

Depois, a fila deve ser processada por `/todos-promote-ekaite` ou por automação equivalente. Ao criar a task, a rotina precisa gravar `ekaite_task_id` no `todos-data.json` e regenerar o dashboard para a tag mudar para `✓ Ekyte #1234`.

## Regras de dedup

O dedup principal hoje usa:

- `processed_file_ids` em `.todos/last-sync.json`;
- ids estáveis dos itens no `todos-data.json`;
- `change-log.jsonl` para auditoria.

Padrão de ID recomendado:

```text
s21-YYYYMMDD-origem-slug-curto
```

Exemplo:

```text
s21-20260525-a4-ligar-vladimir
```

## Limitações conhecidas

1. O botão Atualizar cria trigger, mas ainda não consome o trigger automaticamente.
2. A fila Ekyte ainda depende de `/todos-promote-ekaite` para virar task real.
3. A extração final dos to-dos ainda depende de leitura/decisão do agente.
4. As skills originais vivem em `~/.claude/skills`, fora do repo.
5. Existe divergência de regra entre skills antigas:
   - `todos-sync` orienta logar erro de Drive e continuar;
   - `atualiza-todos` orienta pausar em erro de Drive.
6. O dashboard direto via `file://` não pode gravar arquivos; para Ekyte, ele baixa o JSON atualizado como fallback.
