# Instalação do Sistema de To-Dos

Este guia configura o sistema em um Mac novo. Ao final, o usuário terá:

- dashboard local em `http://127.0.0.1:8787/`;
- botão **Atualizar agora** executando o Python diretamente;
- atualização automática a cada duas horas, de segunda a sexta-feira;
- leitura do Google Calendar e das transcrições no Google Drive;
- extração de tasks com Gemini;
- dados, tokens e histórico fora do Git.

## 1. Pré-requisitos

- macOS com usuário conectado;
- Python 3.9 ou superior;
- Git;
- Google Chrome;
- acesso ao Google Calendar e Google Drive da conta utilizada;
- chave da Gemini API;
- credencial OAuth do Google;
- Claude Code ou Codex, caso queira usar as skills.

Valide:

```bash
python3 --version
git --version
```

## 2. Clonar o repositório

```bash
git clone https://github.com/jeffersonvieira-hue/sistema_todos.git
cd sistema_todos
```

## 3. Instalar as skills

```bash
for skill in todos-installer todos-sync atualiza-todos todos-dedup; do
  mkdir -p "$HOME/.claude/skills/$skill"
  cp "Sistema de to do/skills/$skill/SKILL.md" \
    "$HOME/.claude/skills/$skill/SKILL.md"
done
```

Para usar no Codex, copie as mesmas pastas para `~/.codex/skills/`.

## 4. Criar a estrutura do usuário

Exemplo:

```bash
python3 "Sistema de to do/install_todos.py" \
  --name "Ana Souza" \
  --email "ana.souza@empresa.com" \
  --role "gestor-projetos" \
  --bu "Invictus" \
  --squad "Invictus" \
  --yes
```

Funções aceitas:

- `coordenador`;
- `gestor-projetos`;
- `gestor-trafego`;
- `copywriter`;
- `designer`;
- `social-media`;
- `dados-bi`;
- `atendimento-crm`;
- `outro`.

O comando cria:

```text
People/Ana Souza/
├── auto_sync.py
├── generate_dashboard.py
├── setup_google_oauth.py
├── todos-data.json
├── todos-dashboard.html
└── .todos/
```

As pastas em `People/` são pessoais e ignoradas pelo Git.

## 5. Configurar a chave Gemini

Crie o arquivo:

```bash
mkdir -p "$HOME/.config/todos-auto-sync"
printf 'GEMINI_API_KEY=COLE_SUA_CHAVE_AQUI\n' \
  > "$HOME/.config/todos-auto-sync/secrets.env"
chmod 600 "$HOME/.config/todos-auto-sync/secrets.env"
```

Gere a chave em:

```text
https://aistudio.google.com/app/apikey
```

Não salve a chave dentro do repositório.

## 6. Configurar OAuth do Google

O sistema precisa de acesso somente leitura ao Calendar e ao Drive.

### 6.1 Criar credencial

No Google Cloud Console:

1. Crie ou selecione um projeto.
2. Ative a Google Calendar API.
3. Ative a Google Drive API.
4. Configure a tela de consentimento OAuth.
5. Crie uma credencial OAuth do tipo **Aplicativo para computador**.
6. Baixe o JSON.

Salve o arquivo como:

```text
~/.claude/gdrive/credentials.json
```

Comandos:

```bash
mkdir -p "$HOME/.claude/gdrive"
cp "$HOME/Downloads/client_secret_SEU_ARQUIVO.json" \
  "$HOME/.claude/gdrive/credentials.json"
chmod 600 "$HOME/.claude/gdrive/credentials.json"
```

### 6.2 Autorizar a conta

```bash
python3 "People/Ana Souza/setup_google_oauth.py"
```

O navegador abrirá a autorização. Ao concluir, o token será salvo em:

```text
~/.config/todos-auto-sync/google-token.json
```

## 7. Validar as integrações

```bash
python3 "People/Ana Souza/auto_sync.py" --check
```

O retorno deve confirmar:

- Calendar;
- usuário do Drive;
- modelo Gemini disponível.

Não prossiga com a automação se essa validação falhar.

## 8. Configurar Ekyte

Se o usuário utilizar Ekyte:

1. Copie o exemplo:

```bash
cp "Sistema de to do/templates/mcp.example.json" mcp.json
```

2. Preencha os tokens no `mcp.json`.
3. Não faça commit do arquivo.
4. Rode `/todos-installer` para mapear workspace, projetos, tipos, responsáveis e tags.

O botão Ekyte funciona somente com o dashboard aberto pelo servidor local.

## 9. Ativar o dashboard e a automação

```bash
python3 "Sistema de to do/install_automation.py" \
  --name "Ana Souza"
```

O instalador:

- cria uma cópia operacional em `~/Library/Application Support/Todos Ana/`;
- instala o servidor do dashboard;
- instala o agendamento automático;
- executa o sync a cada 7.200 segundos;
- restringe a execução automática a segunda, terça, quarta, quinta e sexta-feira.

Abra:

```text
http://127.0.0.1:8787/
```

## 10. Primeiro teste

Execute uma atualização pequena:

```bash
python3 "People/Ana Souza/auto_sync.py" \
  --from "2026-06-20" \
  --to "2026-06-20" \
  --max-files 1 \
  --dry-run
```

Depois faça uma execução real:

```bash
python3 "People/Ana Souza/auto_sync.py" \
  --from "2026-06-20" \
  --to "2026-06-20" \
  --max-files 1
```

Substitua a data por um dia que tenha reunião com transcrição.

## 11. Testar pelo dashboard

1. Abra `http://127.0.0.1:8787/`.
2. Clique em **Atualizar**.
3. Escolha o período.
4. Clique em **Atualizar agora**.
5. Aguarde o botão liberar.
6. Confira o rodapé e o ícone de informação.

A página será recarregada somente quando a atualização terminar. Não existe consulta a cada 60 segundos.

## 12. Onde ficam os dados

Código versionado:

```text
sistema_todos/
```

Dados locais do usuário:

```text
People/{Nome}/
```

Cópia operacional:

```text
~/Library/Application Support/Todos {PrimeiroNome}/
```

Credenciais:

```text
~/.claude/gdrive/credentials.json
~/.config/todos-auto-sync/google-token.json
~/.config/todos-auto-sync/secrets.env
```

Nenhum desses tokens deve ir para o Git.

## 13. Logs e diagnóstico

Na pasta operacional:

```text
.todos/auto-sync-status.json
.todos/auto-sync-errors.json
.todos/meeting-sync-log.json
.todos/auto-sync-launchd.log
.todos/auto-sync-launchd.err.log
.todos/dashboard-server.log
.todos/dashboard-server.err.log
```

Verifique o dashboard:

```bash
curl http://127.0.0.1:8787/api/status
```

Verifique os serviços:

```bash
launchctl list | grep todos
```

## 14. Atualizar o sistema

```bash
git pull
```

Depois rode novamente:

```bash
python3 "Sistema de to do/install_todos.py" \
  --name "Ana Souza" \
  --email "ana.souza@empresa.com" \
  --role "gestor-projetos" \
  --bu "Invictus" \
  --squad "Invictus" \
  --yes

python3 "Sistema de to do/install_automation.py" --name "Ana Souza"
```

O modo `--yes` preserva `todos-data.json` e os arquivos de estado existentes.

## 15. Checklist final

- [ ] Python 3.9+ instalado.
- [ ] Repositório clonado.
- [ ] Skills copiadas.
- [ ] Usuário criado em `People/{Nome}/`.
- [ ] Chave Gemini salva fora do Git.
- [ ] OAuth Google configurado.
- [ ] `auto_sync.py --check` retornou sucesso.
- [ ] Mapeamento Ekyte concluído, se aplicável.
- [ ] Automação instalada.
- [ ] Dashboard abriu em `127.0.0.1:8787`.
- [ ] Botão **Atualizar agora** executou com sucesso.
- [ ] Rodapé mostrou a última atualização e as tasks novas.
