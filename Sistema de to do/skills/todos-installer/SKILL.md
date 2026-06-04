---
name: todos-installer
description: |
  Instala e configura o Sistema de To-Dos Operacionais V2 para um novo usuário do time.
  Cria o diretório People/{Nome}/, configura user-config.json, ekyte-config.json, gera o
  dashboard inicial e valida a instalação. Use quando alguém do time quiser configurar
  o sistema na própria máquina.
trigger:
  manual: /todos-installer
mcps_required:
  - Google Drive (opcional, para validar acesso)
  - Google Calendar (opcional, para validar acesso)
  - Ekyte (opcional, para validar workspace)
output_files:
  - People/{Nome}/generate_dashboard.py
  - People/{Nome}/todos-data.json
  - People/{Nome}/todos-dashboard.html
  - People/{Nome}/.todos/user-config.json
  - People/{Nome}/.todos/ekyte-config.json
---

# /todos-installer — Instalação do Sistema de To-Dos V2

## Quando usar

- Alguém do time quer instalar o sistema pela primeira vez
- Reinstalação após trocar de máquina
- Configurar para outro usuário ("instala para a Ana Souza, tráfego")
- Atualizar o gerador (`generate_dashboard.py`) preservando dados locais

## Pré-requisitos

Antes de instalar, confirmar que:

1. **Python 3.9+** instalado (`python3 --version`)
2. **Claude Code** instalado com acesso ao repositório `skills_colli_co-main`
3. **Repositório clonado** (ex.: `~/Documents/skills_colli_co-main`)
4. **Template base presente:** `Sistema de to do/templates/base/generate_dashboard.py`
5. **MCP configurado** — copiar `Sistema de to do/templates/mcp.example.json` para `mcp.json` na raiz do repo (ou `~/.claude/mcp.json`) e preencher tokens

O instalador **não depende** da pasta `People/Jefferson Vieira`. O gerador vem do template neutro em `templates/base/`.

---

## Como executar o instalador

### Opção 1 — Interativa (recomendado)

```bash
cd skills_colli_co-main
python3 "Sistema de to do/install_todos.py"
```

### Opção 2 — Com flags (sem interação)

```bash
python3 "Sistema de to do/install_todos.py" \
  --name "Ana Souza" \
  --email "ana.souza@v4company.com" \
  --role "gestor-trafego" \
  --bu "Invictus" \
  --squad "Invictus" \
  --yes
```

Com `--yes` e diretório já existente: preserva `todos-data.json` e `.todos/ekyte-config.json`, atualiza `user-config.json` e o gerador, sem perguntas.

### Funções disponíveis (`--role`)

| Valor | Descrição |
|---|---|
| `coordenador` | Coordenador de BU |
| `gestor-projetos` | Gestor de projetos / atendimento |
| `gestor-trafego` | Gestor de tráfego |
| `copywriter` | Copywriter |
| `designer` | Designer |
| `social-media` | Social Media |
| `dados-bi` | BI / Dados |
| `atendimento-crm` | Atendimento / CRM |
| `outro` | Outra função |

---

## O que o instalador cria

```
People/{Nome do Usuário}/
├── generate_dashboard.py       ← copiado de templates/base/
├── todos-data.json             ← sprint atual (só se não existir)
├── todos-dashboard.html        ← gerado automaticamente
└── .todos/
    ├── user-config.json        ← identidade + preferências (sempre atualizado)
    ├── ekyte-config.json       ← workspaces (só se não existir)
    ├── last-sync.json
    ├── last-alerts.json
    ├── ekyte-pending.json
    ├── ekyte-errors.json
    ├── refresh-errors.json
    └── install-state.json
```

Cada usuário lê apenas arquivos em `People/{Nome}/` — paths relativos ao `BASE_DIR` do próprio `generate_dashboard.py`.

---

## Como validar

```bash
python3 "People/{Nome}/generate_dashboard.py" --validate
python3 "People/{Nome}/generate_dashboard.py" --keep-transcripts
open "People/{Nome}/todos-dashboard.html"
python3 "People/{Nome}/generate_dashboard.py" --serve --keep-transcripts
```

---

## Como configurar MCP

Na raiz do repositório (recomendado para o gerador local):

```bash
cp "Sistema de to do/templates/mcp.example.json" mcp.json
# Editar mcp.json e substituir <PREENCHER_TOKEN_*>
```

O formato usa `npx supergateway` com `--streamableHttp` e `--header Authorization: Bearer ...`, compatível com `load_ekyte_mcp_config()` no gerador.

**Não commitar** `mcp.json` — está no `.gitignore`.

Opcional: copiar a skill para o Claude Code:

```bash
mkdir -p ~/.claude/skills/todos-installer
cp "Sistema de to do/skills/todos-installer/SKILL.md" \
   ~/.claude/skills/todos-installer/SKILL.md
```

Reinicie o Claude Code após alterar MCPs.

---

## Como configurar Ekyte

1. Editar `People/{Nome}/.todos/ekyte-config.json`
2. Preencher `default_workspace_id`, `workspaces`, tipos de task
3. Descobrir IDs: `/ekyte-refresh` no Claude Code
4. Testar: botão **↑ Ekyte** no dashboard (com `--serve` ativo)

---

## Diagnóstico de erros comuns

| Erro | Causa | Solução |
|---|---|---|
| `generate_dashboard.py não encontrado` | Template base ausente | Verificar `Sistema de to do/templates/base/generate_dashboard.py` |
| `Schema validation failed` | `todos-data.json` inválido | Rodar `--validate` e corrigir JSON |
| `MCP Ekyte não encontrado` | `mcp.json` sem servidor `ekyte` | Copiar `mcp.example.json`, preencher token, reiniciar Claude |
| `Port 8787 already in use` | Servidor já rodando | `kill $(lsof -ti:8787)` |
| Dashboard vazio | Categorias erradas | Verificar `user-config.json → dashboard.categories` |
| Instalador pede confirmação com `--yes` | Bug antigo | Usar versão atual do `install_todos.py` com `non_interactive` |

---

## Fluxo completo (Git)

```bash
git clone <repo-url> skills_colli_co-main
cd skills_colli_co-main

cp "Sistema de to do/templates/mcp.example.json" mcp.json
# preencher tokens no mcp.json

mkdir -p ~/.claude/skills/todos-installer
cp "Sistema de to do/skills/todos-installer/SKILL.md" \
   ~/.claude/skills/todos-installer/SKILL.md

python3 "Sistema de to do/install_todos.py" \
  --name "Ana Souza" \
  --email "ana.souza@v4company.com" \
  --role "gestor-trafego" \
  --yes

python3 "People/Ana Souza/generate_dashboard.py" --serve --keep-transcripts
```
