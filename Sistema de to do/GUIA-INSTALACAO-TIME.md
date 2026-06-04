# Guia de Instalação — Sistema de To-Dos Operacionais V2

Instalação para qualquer pessoa do time. Cada usuário trabalha em `People/{Nome}/`.

---

## Você acabou de clonar ou deu `git pull`?

Abra o Claude Code na pasta do repo e rode:

```
/todos-installer
```

Ou execute o lembrete no terminal:

```bash
bash "Sistema de to do/scripts/pos-pull.sh"
```

---

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

## 2. Instalar o sistema (Fase A — Python)

```bash
python3 "Sistema de to do/install_todos.py" \
  --name "Ana Souza" \
  --email "ana.souza@v4company.com" \
  --role "gestor-trafego" \
  --bu "Invictus" \
  --squad "Invictus" \
  --sync-preset last7 \
  --yes
```

Flags de sync:
- `--sync-preset yesterday|last7|custom`
- `--sync-from` / `--sync-to` (com `custom`)
- `--skip-initial-sync` — não grava `refresh-trigger.json`
- `--skip-mapping` — não exige mapeamento ao final (exit 0)

O instalador grava `.todos/refresh-trigger.json` com o range do **primeiro sync** e cria `.todos/mapeamento.md` (esqueleto).

**Exit code 2** = estrutura OK, mapeamento pendente → continuar Fase B.

Modo interativo (pergunta range + integrações):

```bash
python3 "Sistema de to do/install_todos.py"
```

---

## 2b. Mapeamento Ekyte + Cockpit (Fase B — Claude)

Copie as skills para o Claude Code:

```bash
for s in todos-installer todos-sync atualiza-todos todos-dedup; do
  mkdir -p ~/.claude/skills/$s
  cp "Sistema de to do/skills/$s/SKILL.md" ~/.claude/skills/$s/SKILL.md
done
```

No Claude Code:

```
/todos-installer
```

A Fase B vai:
1. Buscar workspaces e projetos no MCP **Ekyte**
2. Buscar projetos e **time** no MCP **Cockpit**
3. Preencher `ekyte-config.json`, `user-config.json` e `mapeamento.md`
4. Rodar primeiro `/atualiza-todos` (usa o range do `refresh-trigger.json`)
5. Desduplicar tasks automaticamente

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

Preferencial: deixar a **Fase B** do `/todos-installer` preencher via MCP.

Manual: edite `People/{Seu Nome}/.todos/ekyte-config.json` e consulte `mapeamento.md`.

Opção **Outros**: nos selects do modal Ekyte, escolha "Outros (informar ID)" e digite o ID/e-mail manualmente.

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
| `People/{Nome}/.todos/ekyte-config.json` | Workspaces, projetos, assignees Ekyte |
| `People/{Nome}/.todos/mapeamento.md` | Documento de mapeamento Ekyte + Cockpit |
| `People/{Nome}/.todos/refresh-trigger.json` | Range do primeiro sync |
| `People/{Nome}/.todos/install-state.json` | `mapping_status`: pending \| complete |
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
