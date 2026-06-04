# Operação Diária

Este é o runbook para atualizar os to-dos do Jefferson a partir das reuniões do dia anterior.

## Fluxo rápido

1. Baixar eventos e transcrições do dia anterior.
2. Processar uma transcrição por vez.
3. Adicionar/atualizar itens no `todos-data.json`.
4. Atualizar `last-sync.json` e `change-log.jsonl`.
5. Validar schema.
6. Regenerar dashboard.
7. Abrir via servidor local.

## 1. Baixar eventos e transcrições

Para uma data específica:

```bash
python3 "People/Jefferson Vieira/todos_probe_one_event.py" --date 2026-05-25 --all
```

Isso cria/atualiza:

```text
People/Jefferson Vieira/.todos/manifest-2026-05-25.json
People/Jefferson Vieira/.todos/transcripts/
```

Quando o script precisar de rede, rode com permissão/escalation se o ambiente exigir.

## 2. Processar uma transcrição por vez

Use leituras pequenas para não estourar contexto:

```bash
sed -n '1,140p' "People/Jefferson Vieira/.todos/transcripts/ARQUIVO.txt"
```

Busque sinais de compromisso:

```bash
rg -n -C 2 'Jefferson Vieira|Jefferson|vou |deixa comigo|puxar|passar|alinhar|acompanhar|verificar|garantir|fechou|próxim|pendência|combinado' "People/Jefferson Vieira/.todos/transcripts/ARQUIVO.txt"
```

Critérios para virar to-do:

- Jefferson assumiu fazer algo.
- Jefferson pediu para alguém fazer e precisa cobrar.
- Há decisão estratégica que precisa validação.
- Há follow-up de cliente/projeto sob responsabilidade dele.
- Há risco que, como coordenador, ele precisa acompanhar.

Regra especial para `Comitê Ops - Gerência Invictus` e `[Daily] - Coordenação/Gerência`:

- Só puxar tarefa nominalmente do Jefferson, assumida por ele ou direcionada a todos os coordenadores.
- Puxar acompanhamento se a pauta exigir que Jefferson cobre/garanta algo como coordenador da BU Invictus.
- Não puxar tarefa de outro coordenador apenas porque apareceu na reunião.

Critérios para não virar to-do:

- Apenas contexto informativo.
- Tarefa claramente de outra pessoa sem necessidade de follow-up de coordenação.
- Comentário solto sem ação, prazo ou responsabilidade.
- Nos eventos de coordenação/gerência, tarefa com owner nominal de outro coordenador e sem cobrança coletiva.

Quando for acompanhamento de terceiro, escrever no título como acompanhamento:

```text
Acompanhar ...
Cobrar ...
Garantir ...
Validar ...
```

## 3. Atualizar `todos-data.json`

Adicionar itens na categoria correta:

| Categoria | Quando usar |
| --- | --- |
| `alertas` | Riscos automáticos do Cockpit/Pipeline B. |
| `financeiro` | Contratos, pagamentos, break even, verba. |
| `projetos` | Clientes, contas, check-ins, ações de projeto. |
| `processos` | CRM, BI, tracking, playbooks, ferramentas, Ekyte, Flow. |
| `equipe` | 1:1, entrevista, feedback, time, contratação. |
| `recorrentes` | Rotinas semanais. |

Campos mínimos:

```json
{
  "id": "s21-20260525-origem-slug",
  "title": "Título acionável",
  "context": "Contexto suficiente para executar/cobrar.",
  "priority": "urgente",
  "done": false,
  "source": "Nome da call — 25/05/2026 00:12:34",
  "confidence": "alta",
  "review_needed": false,
  "source_timestamp": "00:12:34",
  "source_quote": "Trecho curto de evidência.",
  "auto_added_at": "2026-05-26T20:19:05-03:00"
}
```

Prioridades válidas:

- `urgente`
- `normal`
- `recorrente`

Confianças usadas:

- `alta`: fala/assunção clara.
- `média`: acompanhamento de coordenação, autoria indireta ou inferência forte.

Use `review_needed: true` quando:

- o item depende de checagem;
- a execução é de terceiro;
- o trecho não deixa 100% claro se Jefferson é dono;
- é um alerta/risco para acompanhamento.

## 4. Atualizar estado do sync

Arquivo:

```text
People/Jefferson Vieira/.todos/last-sync.json
```

Atualizar:

- `last_sync_at`;
- `last_meeting_processed`;
- `processed_file_ids`;
- estatísticas.

Adicionar linha em:

```text
People/Jefferson Vieira/.todos/change-log.jsonl
```

Formato recomendado:

```json
{"ts":"2026-05-26T20:19:05-03:00","mode":"calendar_drive_transcript_batch","range":"2026-05-25/2026-05-25","file_id":"...","file_name":"...","items_added":3,"items_deduped":0,"review_needed":2}
```

## 5. Validar e gerar dashboard

Validar:

```bash
python3 "People/Jefferson Vieira/generate_dashboard.py" --validate
```

Gerar:

```bash
python3 "People/Jefferson Vieira/generate_dashboard.py"
```

Checar JS embutido:

```bash
node -e "const fs=require('fs');const html=fs.readFileSync('People/Jefferson Vieira/todos-dashboard.html','utf8');const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);for(const script of scripts){new Function(script)};console.log('js-ok', scripts.length);"
```

Checar contagem:

```bash
jq '{total: ([.sprints[.meta.currentSprint].categories[].items[]] | length), urgent: ([.sprints[.meta.currentSprint].categories[].items[] | select(.priority=="urgente")] | length), review_needed: ([.sprints[.meta.currentSprint].categories[].items[] | select(.review_needed==true)] | length)}' "People/Jefferson Vieira/todos-data.json"
```

## 6. Abrir dashboard

Para só visualizar:

```bash
open -a "Google Chrome" "/Users/jeffersonvieira/Documents/skills_colli_co-main/People/Jefferson Vieira/todos-dashboard.html"
```

Para botões funcionarem:

```bash
python3 "People/Jefferson Vieira/generate_dashboard.py" --serve --port 8787
```

Depois abrir:

```bash
open -a "Google Chrome" "http://127.0.0.1:8787/"
```

## 7. Botão Atualizar

No servidor local, o botão:

1. Envia `POST /api/refresh`.
2. Grava `.todos/refresh-trigger.json`.
3. Regenera o dashboard.

Se o HTML estiver aberto como `file://`, o dashboard tenta chamar `http://127.0.0.1:8787/api/refresh` antes de cair no fallback.

Ainda falta um consumidor automático do trigger. Até isso existir, quando houver `refresh-trigger.json`, um agente precisa rodar o pipeline manualmente e depois apagar o trigger.

## 8. Botão Adicionar task

No servidor local, o botão:

1. Abre um formulário com categoria, título, prioridade, confiança, contexto, fonte e revisão.
2. Envia `POST /api/manual-task`.
3. Grava o item em `todos-data.json` na sprint atual.
4. Regenera `todos-dashboard.html`.
5. Mostra o item imediatamente na tela.

Sem servidor local, o dashboard copia os dados da task para a área de transferência.

## 9. Botão Ekyte

No servidor local, o botão:

1. Envia `POST /api/ekyte-queue`.
2. Grava/atualiza `.todos/ekyte-pending.json`.
3. Marca visualmente como pendente.

Sem servidor local, o botão:

1. tenta ler `.todos/ekyte-pending.json`;
2. assume `SYSTEM_STATE.ekyte_pending` se não conseguir;
3. adiciona o item elegível;
4. tenta `POST /write-json`;
5. baixa `ekyte-pending.json` atualizado;
6. copia o JSON da fila.

Nesse caso, substituir manualmente:

```text
People/Jefferson Vieira/.todos/ekyte-pending.json
```

com o arquivo baixado antes de processar a fila.

Depois processar com `/todos-promote-ekaite` ou automação equivalente.

Se o header mostrar **Processar fila Ekyte (N)**, clicar nele copia o comando:

```text
/todos-promote-ekaite
```

Antes de finalizar uma rodada, confira:

```bash
test -f "People/Jefferson Vieira/.todos/ekyte-pending.json" && jq length "People/Jefferson Vieira/.todos/ekyte-pending.json" || printf 'no-ekyte-pending\n'
```
