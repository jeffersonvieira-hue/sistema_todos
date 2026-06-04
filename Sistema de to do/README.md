# Sistema de To-Dos Operacionais V2

Sistema instalável para qualquer pessoa do time Colli&Co / V4. Cada usuário tem sua pasta em `People/{Nome}/` com gerador, JSON de to-dos e dashboard HTML.

**Novos usuários não dependem de nenhuma pasta pessoal já existente** — o instalador cópia o gerador de `templates/base/`.

## Como funciona a pasta People

A pasta `People/` no Git contém apenas `.gitkeep`.

Cada usuário cria a própria pasta localmente ao rodar:

```bash
python3 "Sistema de to do/install_todos.py" --name "Nome Pessoa" ...
```

Exemplo gerado localmente (não versionado):

```text
People/Ana Souza/
  generate_dashboard.py
  todos-data.json
  todos-dashboard.html
  .todos/user-config.json
```

Essas pastas pessoais **não devem ser commitadas** (`.gitignore`: `People/*`, exceção `People/.gitkeep`).

Quem já usa o sistema (ex.: Jefferson) mantém `People/{Nome}/` só na máquina local; isso não entra no clone do time.

## Instalação rápida (time)

```bash
git clone <repo-url> skills_colli_co-main
cd skills_colli_co-main

cp "Sistema de to do/templates/mcp.example.json" mcp.json
# preencher tokens no mcp.json (não commitar)

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

Guia completo: [GUIA-INSTALACAO-TIME.md](GUIA-INSTALACAO-TIME.md)

## Arquitetura por usuário

```text
People/{Nome}/
├── generate_dashboard.py    ← BASE_DIR = esta pasta
├── todos-data.json
├── todos-dashboard.html
└── .todos/
    ├── user-config.json
    ├── ekyte-config.json
    └── ...
```

O gerador resolve paths relativos ao próprio diretório:

- `DATA_PATH` = `todos-data.json` ao lado do script
- `STATE_DIR` = `.todos/` ao lado do script
- `REPO_DIR` = raiz do repositório (dois níveis acima)

Template neutro (versionado): `templates/base/generate_dashboard.py`

## Instalador

```bash
python3 "Sistema de to do/install_todos.py" --help
```

| Artefato | Função |
|---|---|
| `install_todos.py` | Cria/atualiza `People/{Nome}/` |
| `templates/base/generate_dashboard.py` | Fonte do gerador (não usa Jefferson) |
| `templates/mcp.example.json` | Modelo MCP (supergateway + streamable HTTP) |
| `templates/categories/*.json` | Categorias por função |
| `skills/todos-installer/SKILL.md` | Skill `/todos-installer` |

## Comandos do gerador

Substitua `{Nome}` pelo usuário instalado:

```bash
python3 "People/{Nome}/generate_dashboard.py" --validate
python3 "People/{Nome}/generate_dashboard.py"
python3 "People/{Nome}/generate_dashboard.py" --serve --port 8787
python3 "People/{Nome}/generate_dashboard.py" --keep-transcripts
```

## Pipelines (Claude Code)

| Comando | Pipeline |
|---|---|
| `/atualiza-todos` | A — sync transcrições → `todos-data.json` |
| `/todos-project-alerts` | B — alertas Cockpit (coordenadores) |
| `/todos-installer` | Instalação de novo usuário |

## Segurança e Git

Não commitar:

- `People/{Nome}/` (dados e dashboard de cada usuário)
- `mcp.json` / `**/mcp.json` (tokens)
- `Sistema de to do/backups/` (snapshots locais)
- `**/.todos/transcripts/` e `**/.todos/archive/`

Ver `.gitignore` na raiz do repositório.

## Documentação

| Documento | Conteúdo |
|---|---|
| [GUIA-INSTALACAO-TIME.md](GUIA-INSTALACAO-TIME.md) | Instalação para o time |
| [GUIA-USO-DIARIO.md](GUIA-USO-DIARIO.md) | Uso diário |
| [GUIA-CONFIGURACAO-EKYTE.md](GUIA-CONFIGURACAO-EKYTE.md) | Ekyte |
| [GUIA-FUNCOES.md](GUIA-FUNCOES.md) | Categorias por função |
| [ARQUITETURA.md](ARQUITETURA.md) | Componentes e fluxos |
| [HANDOFF_AGENTES.md](HANDOFF_AGENTES.md) | Handoff para agentes |

## Regra de ouro

Nunca edite só o HTML para mudar to-dos. Edite `todos-data.json` e rode o gerador.

Instalações locais antigas (ex.: coordenador que já usava o sistema antes do template neutro) continuam em `People/{Nome}/` na máquina de cada um, fora do Git.
