# Guia de Configuração Ekyte — Sistema de To-Dos V2

## Arquivo de configuração

```
People/{Seu Nome}/.todos/ekyte-config.json
```

---

## Campos principais

```json
{
  "default_workspace_id": "112225",
  "default_assignee_email": "seu@v4company.com",
  "default_task_type_id": "68301",
  "workspaces": [
    {
      "id": "112225",
      "name": "[Invictus][BU] Planos de ação",
      "projects": [
        { "id": "216299", "name": "[Invictus][BU] Planos de ação" }
      ],
      "task_types": [
        { "id": "68301", "name": "Tipo Padrão" }
      ]
    }
  ]
}
```

---

## Como descobrir os IDs

### Via Claude Code

```
/ekyte-refresh
```

O sistema vai buscar seus workspaces, projetos e tipos de task e preencher o `ekyte-config.json` automaticamente.

### Manualmente no Ekyte

1. Acesse `app.ekyte.com`
2. Vá em **Configurações → Workspaces**
3. Copie o ID do workspace da URL
4. Vá em **Tarefas → Tipos de Tarefa** para os IDs de tipo

---

## Tags obrigatórias

O sistema exige duas tags em toda task criada:
- **Tag de rotina** (ex: AÇÃO GERENCIAL, QUALITY CONTROL, WEEKLY EXPANSÃO)
- **Tag de semana** (ex: SEMANA 23)

Se os IDs das tags não estiverem preenchidos, o sistema vai:
- Criar a task no Ekyte
- Marcar `Ekyte sem tag` (tag laranja no dashboard)
- Você precisa adicionar as tags manualmente no Ekyte

### Preencher IDs das tags

No `ekyte-config.json`, preencha o campo `id` de cada tag:

```json
"routine_tags": [
  { "name": "AÇÃO GERENCIAL", "id": "12345" },
  { "name": "QUALITY CONTROL", "id": "12346" }
],
"week_tags": [
  { "name": "SEMANA 23", "id": "67890" }
]
```

Para descobrir os IDs: use o MCP Ekyte com `/ekyte-refresh` ou consulte o Jefferson.

---

## Erros comuns

| Erro no dashboard | Causa | Solução |
|---|---|---|
| `MCP Ekyte não expôs campo de tags` | MCP sem token ou URL errada | Verificar `~/.claude/mcp.json` |
| `Ekyte sem tag` (laranja) | Tag IDs não preenchidos | Preencher `ekyte-config.json` e/ou adicionar tag manualmente |
| Task criada mas sem link | ID não retornado pelo Ekyte | Verificar manualmente em `app.ekyte.com` |
| Workspace ID null | Config não preenchida | Rodar `/ekyte-refresh` ou preencher manualmente |

---

## Workflow recomendado

1. Instalar sistema (`install_todos.py`)
2. Rodar `/ekyte-refresh` no Claude Code
3. Verificar se workspaces e projetos foram preenchidos
4. Testar com 1 task de baixa criticidade
5. Confirmar no Ekyte que apareceu com tags corretas
