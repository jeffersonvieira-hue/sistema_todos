# Release V1 - Sistema de To Dos Jefferson Vieira

## Data

2026-06-04

## Status

Versão consolidada como V1 funcional.

## Escopo da V1

- Dashboard local self-contained.
- Servidor local em Python na porta `8787`.
- Botão Atualizar com criação de trigger.
- Entrada manual de task.
- Conclusão de task com modal e anotação.
- Histórico e follow.
- Filtros, busca e visualização densa.
- Fila Ekyte.
- Criação direta no Ekyte via MCP local.
- Modal Ekyte com workspace, projeto, tipo, responsável, prazo, rotina e semana.
- Gravação do ID Ekyte no todo após criação real.
- Link correto da task Ekyte no formato:

```text
https://app.ekyte.com/#/tasks/list/{TASK_ID}/edit
```

## Arquivos principais

- `People/Jefferson Vieira/generate_dashboard.py`
- `People/Jefferson Vieira/todos-data.json`
- `People/Jefferson Vieira/todos-dashboard.html`
- `People/Jefferson Vieira/.todos/`
- `mcp.example.json`
- `refs/time.md`
- `refs/playbook-tags-ekyte.md`

## Estado da base no fechamento

- Total de itens: 155.
- Itens com ID Ekyte registrado: 4.
- Categorias: 6.
- Backup privado: `Sistema de to do/backups/V1-2026-06-04_101050`.
- Zip privado: `Sistema de to do/backups/V1-2026-06-04_101050.zip`.
- Pacote distribuível: `Sistema de to do/releases/todos-jefferson-v1`.

## Como restaurar a partir do pacote

1. Copie o pacote para a nova máquina.
2. Configure `mcp.json` a partir de `mcp.example.json`.
3. Rode `bash scripts/check_install.sh`.
4. Rode `bash scripts/start_dashboard.sh`.

## Critério de aceite da V1

- O dashboard abre em `http://127.0.0.1:8787`.
- O HTML regenera sem erro.
- A validação do JSON passa.
- A fila Ekyte valida as tags antes de criar.
- Uma task criada no Ekyte volta para o dashboard com `✓ Ekyte #ID`.
- O link `✓ Ekyte #ID` abre a task no Ekyte sem 404.
