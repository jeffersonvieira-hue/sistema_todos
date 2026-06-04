# Guia de Instalação — Sistema de To-Dos Operacionais V2

Instalação para qualquer pessoa do time. Cada usuário trabalha em `People/{Nome}/`. A V1 do Jefferson **não é dependência** do instalador — o gerador vem de `Sistema de to do/templates/base/generate_dashboard.py`.

## Requisitos

- macOS com Python 3.9+
- Claude Code instalado
- Repositório `skills_colli_co-main` clonado
- Tokens MCP (Ekyte, Cockpit; BigQuery se coordenador)

---

## 1. Clonar e preparar MCP

```bash
git clone <repo-url> skills_colli_co-main
cd skills_colli_co-main

cp "Sistema de to do/templates/mcp.example.json" mcp.json
```

Edite `mcp.json` na raiz do repo e substitua os placeholders `<PREENCHER_TOKEN_*>` pelos tokens reais.

**Não commite** `mcp.json` — o arquivo está no `.gitignore`.

Formato esperado: `npx supergateway` com `--streamableHttp` e header `Authorization: Bearer ...` (compatível com o gerador).

Opcional — skill no Claude Code:

```bash
mkdir -p ~/.claude/skills/todos-installer
cp "Sistema de to do/skills/todos-installer/SKILL.md" \
   ~/.claude/skills/todos-installer/SKILL.md
```

Reinicie o Claude Code após salvar o MCP.

---

## 2. Instalar o sistema

```bash
python3 "Sistema de to do/install_todos.py" \
  --name "Ana Souza" \
  --email "ana.souza@v4company.com" \
  --role "gestor-trafego" \
  --bu "Invictus" \
  --squad "Invictus" \
  --yes
```

Modo interativo (sem flags):

```bash
python3 "Sistema de to do/install_todos.py"
```

O instalador pergunta nome, e-mail, BU, função e integrações.

**Reinstalação / atualização** (mesmo comando com `--yes`):

- Preserva `todos-data.json`
- Preserva `.todos/ekyte-config.json`
- Atualiza `user-config.json` e `generate_dashboard.py`
- Não pede confirmação no modo `--yes`

---

## 3. Abrir o dashboard

```bash
open "People/Ana Souza/todos-dashboard.html"
```

Servidor local (botões Atualizar e Ekyte gravando em disco):

```bash
python3 "People/Ana Souza/generate_dashboard.py" --serve --keep-transcripts
```

Acesse: `http://127.0.0.1:8787`

Validar JSON:

```bash
python3 "People/Ana Souza/generate_dashboard.py" --validate
```

---

## 4. Configurar Ekyte

Edite `People/{Seu Nome}/.todos/ekyte-config.json`:

- `default_workspace_id`
- `workspaces` com projetos e tipos de task

Descobrir IDs: `/ekyte-refresh` no Claude Code.

---

## 5. Primeiro sync

No Claude Code:

```
/atualiza-todos
```

Lê transcrições das reuniões e preenche o backlog (Pipeline A). Coordenadores também podem usar alertas de projeto (Pipeline B) se Cockpit estiver no `mcp.json`.

---

## Como funciona a pasta People

No repositório Git, `People/` contém apenas `.gitkeep`.

Cada pessoa cria a própria pasta ao instalar:

```bash
python3 "Sistema de to do/install_todos.py" --name "Nome Pessoa" ...
```

Exemplo gerado **localmente** (ignorado pelo Git):

```text
People/Ana Souza/
  generate_dashboard.py
  todos-data.json
  todos-dashboard.html
  .todos/user-config.json
```

Não commite pastas em `People/{Nome}/`.

---

## Onde ficam os arquivos

| Caminho | Conteúdo |
|---|---|
| `People/{Nome}/generate_dashboard.py` | Gerador + servidor local |
| `People/{Nome}/todos-data.json` | Fonte de verdade dos to-dos |
| `People/{Nome}/.todos/user-config.json` | Identidade e categorias |
| `People/{Nome}/.todos/ekyte-config.json` | Workspaces Ekyte |
| `mcp.json` (raiz do repo) | Tokens MCP — **local, ignorado pelo Git** |
| `Sistema de to do/backups/` | Backups locais — **ignorado pelo Git** |
| `Sistema de to do/templates/base/` | Template neutro do gerador |
| `People/.gitkeep` | Único artefato versionado em `People/` |

---

## Problemas comuns

| Problema | Solução |
|---|---|
| `Port 8787 already in use` | `kill $(lsof -ti:8787)` |
| Dashboard vazio | Verificar `user-config.json → dashboard.categories` |
| `MCP Ekyte não encontrado` | Verificar `mcp.json` na raiz e reiniciar Claude |
| `Schema validation failed` | `python3 "People/{Nome}/generate_dashboard.py" --validate` |
| Instalador pede sobrescrever com `--yes` | Atualizar `install_todos.py` do repo |

---

## Documentação relacionada

- [README.md](README.md) — visão geral e comandos
- [GUIA-USO-DIARIO.md](GUIA-USO-DIARIO.md) — rotina diária
- [GUIA-CONFIGURACAO-EKYTE.md](GUIA-CONFIGURACAO-EKYTE.md) — Ekyte em detalhe
- [skills/todos-installer/SKILL.md](skills/todos-installer/SKILL.md) — skill para Claude Code
