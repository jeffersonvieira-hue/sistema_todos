# Guia de Configuração Ekyte — Sistema de To-Dos V2

## Arquivos de configuração

```
People/{Seu Nome}/.todos/ekyte-config.json   ← IDs Ekyte + assignees
People/{Seu Nome}/.todos/mapeamento.md       ← documento legível (gerado na instalação)
People/{Seu Nome}/.todos/user-config.json    ← cockpit.project_document_ids
```

---

## Mapeamento automático (recomendado)

```
/todos-installer
```

Fase B busca no MCP:
- **Ekyte:** workspaces, projetos, tipos de task, tags
- **Cockpit:** projetos da BU + time (coord/GT/e-mails → `assignees`)

Resultado gravado em `ekyte-config.json`, `user-config.json` e `mapeamento.md`.

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
        { "id": "216299", "name": "[Invictus][BU] Planos de ação" },
        { "id": "__other__", "name": "Outros (informar ID)", "is_other": true }
      ],
      "task_types": [
        { "id": "68301", "name": "Tipo Padrão" }
      ]
    }
  ],
  "assignees": [
    { "name": "Você", "email": "seu@v4company.com", "role": "Gestor" },
    { "id": "__other__", "name": "Outros (informar e-mail)", "is_other": true }
  ]
}
```

---

## Opção "Outros"

Quando um workspace, projeto, tipo ou pessoa não aparece no MCP:

1. Registre em `mapeamento.md` → **Pendências manuais**
2. No dashboard, modal **↑ Ekyte**, selecione **Outros (informar ID)**
3. Digite o ID ou e-mail no campo que aparece abaixo do select

---

## Tags obrigatórias

O sistema exige duas tags em toda task criada:
- **Tag de rotina** (ex: AÇÃO GERENCIAL, QUALITY CONTROL)
- **Tag de semana** (ex: SEMANA 23)

Preencha o campo `id` em `routine_tags` e `week_tags` no `ekyte-config.json` (Fase B do installer faz isso via `list_tags`).

---

## Time (fonte: Cockpit)

`assignees[]` é populado principalmente pelo Cockpit na instalação:
- Coordenadores, GTs, accounts, mídia, etc. da BU
- Sempre inclui o usuário instalado
- Entrada `__other__` para e-mails não listados

---

## Erros comuns

| Erro | Causa | Solução |
|---|---|---|
| `mapping_status: pending` | Fase B não rodou | `/todos-installer` |
| Workspace ID null | Mapeamento incompleto | Fase B ou Outros no modal |
| `Ekyte sem tag` | Tag IDs vazios | Preencher tags no config |
| Time vazio no select | Cockpit não consultado | Rodar Fase B |

---

## Workflow recomendado

1. `install_todos.py` com `--sync-preset last7`
2. `/todos-installer` (Fase B)
3. `/atualiza-todos` (primeiro sync + dedup)
4. Testar 1 task via **↑ Ekyte**
5. Confirmar no `app.ekyte.com`
