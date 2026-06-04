# Handoff para Agentes

Este documento é para Codex, Claude ou qualquer outro agente assumir o sistema sem perder contexto.

## Primeira leitura obrigatória

Leia nesta ordem:

1. `Sistema de to do/README.md`
2. `Sistema de to do/ARQUITETURA.md`
3. `Sistema de to do/OPERACAO_DIARIA.md`
4. `People/Jefferson Vieira/README.md`
5. `People/Jefferson Vieira/todos-data.json`
6. `People/Jefferson Vieira/generate_dashboard.py`
7. `People/Jefferson Vieira/todos_probe_one_event.py`

Se estiver disponível, leia também as skills originais do Claude:

| Arquivo | Papel |
| --- | --- |
| `~/.claude/skills/atualiza-todos/SKILL.md` | Orquestrador histórico: Pipeline A + B. |
| `~/.claude/skills/todos-sync/SKILL.md` | Pipeline A: extração de reuniões. |
| `~/.claude/skills/todos-project-alerts/SKILL.md` | Pipeline B: alertas do Cockpit. |
| `~/.claude/skills/todos-project-alerts/lib/cockpit-signals.md` | Detectores de sinal do Cockpit. |
| `~/.claude/skills/todos-sync/prompts/extract-jefferson-todos.md` | Prompt de extração verbal. |
| `~/.claude/skills/todos-promote-ekaite/SKILL.md` | Promoção para Ekyte. |

## Contexto funcional

O Jefferson quer que, todo início de dia, o dashboard já mostre tudo que ele precisa fazer a partir das calls do dia anterior.

Ele não quer uma ata. Ele quer uma lista acionável.

Além de falas assumidas diretamente por ele, também devem virar to-do:

- pendências que ele precisa acompanhar como coordenador;
- cobranças de terceiros;
- riscos em cliente/projeto;
- decisões que exigem validação;
- planos que precisam entrar no Ekyte, Flow, CRM ou check-in.

## Estado pós-migração Claude -> Codex

O que foi implementado/ajustado no Codex:

- `generate_dashboard.py` criado para substituir geração inline por script isolado.
- `todos-dashboard.html` regenerado a partir do JSON.
- Dashboard ganhou:
  - busca inline;
  - filtros/chips;
  - progresso;
  - painel de estado;
  - botão Atualizar com endpoint local;
  - botão `↑ Ekyte` por tarefa elegível.
- `todos_probe_one_event.py` criado para baixar agenda/transcrições via APIs locais.
- Sprint atual foi limpa e reconstruída com reuniões de 2026-05-25.
- Foram processadas 9 transcrições de 2026-05-25.
- Resultado final: 38 to-dos ativos.

## Datas importantes

Data base atual do ambiente: 2026-05-26.

Dia processado na última rodada: 2026-05-25.

Backup criado ao limpar a sprint:

```text
People/Jefferson Vieira/.todos/archive/todos-reset-S21-20260526T200710.json
```

Manifest de transcrições:

```text
People/Jefferson Vieira/.todos/manifest-2026-05-25.json
```

## Transcrições processadas em 2026-05-25

| ID | Reunião | Resultado |
| --- | --- | --- |
| `1A7zyyV6Vxg-jf0_SKhpU9MW5yVmcI0iDS0UdkppY5bw` | Comitê Ops - Gerência Invictus | 3 itens no teste inicial. |
| `1jqDZMu8I4pbwj4EjSV1zHvtXM6WwlFlw8l33i-kD9kM` | Comitê Ops Coord. Jefferson Vieira | 5 itens. |
| `1ZnnIPsMj44EHu9IqcYr7DnU6gPf20JgreP8H-0hMHmo` | O3NT Semanal | 4 itens de acompanhamento. |
| `1mXUuHAHkGtagwzK4JExUzh0kAedHfmdTdQLV4Grmk58` | Sprint Planning CRM & BI | 7 itens de acompanhamento. |
| `131vN0hSkX-sBu8rmGvQa9SaUORAKnxRIVlj4pkW_ouk` | Entrevista Coordenação GT Vinícius Bispo | 2 itens. |
| `1B6gP6BXiNm-nn3vejZjkkQzTr7NLzeBp3qvC6Wy9YRo` | AQTR 1a1 Aquatro | 3 itens. |
| `10slpsEM9Uawi_Z39sRWEBr1WL7nkj7ej6d00uXCcM7E` | Sprint Growth G&D | 3 itens. |
| `1T0RNPXPCtwLrcjw2wjBypc4xu7ON4Puvse_NufhUXwk` | Sprint Growth M&T | 5 itens. |
| `1aDU8J28RKnEK0lIoOZZe9VhOwAtytoBRbeqklIaX_p0` | Sprint Growth T&J | 5 itens. |

## Regras de escrita

Não sobrescrever alterações do usuário.

Não editar `todos-dashboard.html` diretamente para mudar to-dos.

Não apagar `.todos/archive/`.

Não commitar tokens ou trechos de credenciais.

Ao adicionar to-dos:

- manter ids estáveis;
- incluir `source`;
- incluir `source_timestamp` quando houver;
- incluir `source_quote` curto;
- marcar `review_needed` corretamente;
- atualizar `last-sync.json`;
- registrar `change-log.jsonl`;
- rodar validação e geração.

## Checklist antes de responder ao Jefferson

```bash
python3 "People/Jefferson Vieira/generate_dashboard.py" --validate
python3 "People/Jefferson Vieira/generate_dashboard.py"
node -e "const fs=require('fs');const html=fs.readFileSync('People/Jefferson Vieira/todos-dashboard.html','utf8');const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);for(const script of scripts){new Function(script)};console.log('js-ok', scripts.length);"
jq '{total: ([.sprints[.meta.currentSprint].categories[].items[]] | length), urgent: ([.sprints[.meta.currentSprint].categories[].items[] | select(.priority=="urgente")] | length), review_needed: ([.sprints[.meta.currentSprint].categories[].items[] | select(.review_needed==true)] | length)}' "People/Jefferson Vieira/todos-data.json"
```

Se o usuário pedir para abrir o dashboard:

```bash
open -a "Google Chrome" "/Users/jeffersonvieira/Documents/skills_colli_co-main/People/Jefferson Vieira/todos-dashboard.html"
```

Se o usuário perguntar se o botão Atualizar funciona:

```bash
python3 "People/Jefferson Vieira/generate_dashboard.py" --serve --port 8787
open -a "Google Chrome" "http://127.0.0.1:8787/"
```

Explique que o botão grava o trigger; ainda falta o consumidor automático que executa o pipeline completo.

## Perguntas que não devem ser feitas se dá para descobrir

Não perguntar qual é a pasta, data ou arquivo se:

- a data é "ontem" e o ambiente tem data atual;
- o JSON e dashboard existem em `People/Jefferson Vieira/`;
- o manifest da data já existe em `.todos/`;
- as transcrições já estão baixadas em `.todos/transcripts/`.

O padrão é investigar localmente e executar.

