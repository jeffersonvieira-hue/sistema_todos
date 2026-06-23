# Sistema de To-Dos

Dashboard local que transforma reuniões do Google Calendar e transcrições do Drive em tasks.
O pipeline Python usa Gemini para extrair compromissos, evita duplicatas e atualiza o dashboard
automaticamente.

## Instalação

Guia completo para configurar um computador novo: [INSTALACAO.md](INSTALACAO.md).

```bash
git clone https://github.com/jeffersonvieira-hue/sistema_todos.git
cd sistema_todos
```

Copie as skills:

```bash
for skill in todos-installer todos-sync atualiza-todos todos-dedup; do
  mkdir -p "$HOME/.claude/skills/$skill"
  cp "Sistema de to do/skills/$skill/SKILL.md" "$HOME/.claude/skills/$skill/SKILL.md"
done
```

Depois rode `/todos-installer` no Claude Code ou use diretamente:

```bash
python3 "Sistema de to do/install_todos.py" \
  --name "Nome da Pessoa" \
  --email "pessoa@empresa.com" \
  --role "coordenador" \
  --yes
```

Para uma função fora da lista:

```bash
python3 "Sistema de to do/install_todos.py" \
  --name "Nome da Pessoa" \
  --email "pessoa@empresa.com" \
  --role "outro" \
  --role-label "Nome da função" \
  --role-rules "Responsabilidade 1;Responsabilidade 2" \
  --yes
```

No modo interativo, o instalador pergunta esses dados e adapta as regras de extração.

## Automação

```bash
python3 "Sistema de to do/install_automation.py" --name "Nome da Pessoa"
```

Esse comando:

- mantém o dashboard em `http://127.0.0.1:8787/`;
- executa o sync a cada duas horas, de segunda a sexta;
- permite que o botão **Atualizar agora** rode o Python sob demanda;
- oferece temas claro e escuro com preferência salva no navegador;
- recarrega a tela apenas quando uma atualização termina;
- mantém tokens e dados pessoais fora do Git.

Documentação: [`Sistema de to do/README.md`](Sistema%20de%20to%20do/README.md).
