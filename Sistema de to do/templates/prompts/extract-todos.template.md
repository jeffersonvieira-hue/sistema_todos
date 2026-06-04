# Prompt de Extração de To-Dos — Template Parametrizado

## Identidade do usuário

- **Nome completo:** {{USER_FULL_NAME}}
- **Nome curto:** {{USER_DISPLAY_NAME}}
- **E-mail:** {{USER_EMAIL}}
- **Função:** {{USER_ROLE_LABEL}}
- **Aliases reconhecidos:** {{OWNER_ALIASES}}

## Regra principal

Extraia somente tarefas que se enquadrem em uma das categorias abaixo:

1. **Atribuição direta:** a transcrição menciona explicitamente `{{USER_DISPLAY_NAME}}` ou `{{USER_FULL_NAME}}` como responsável.
2. **Grupo do usuário:** a tarefa é direcionada ao grupo do qual a pessoa faz parte (ex: "todos os coordenadores", "a equipe de tráfego") E é coerente com a função configurada.
3. **Comprometimento verbal:** o próprio usuário fala na reunião frases como "fico de", "vou ver", "deixa comigo", "me responsabilizo" — desde que seja sobre algo dentro do escopo da função.
4. **Acompanhamento obrigatório:** `{{CAPTURE_FOLLOW_UPS}}` — se true, capturar follow-ups de projetos/clientes sob responsabilidade do usuário mesmo sem ação direta.

## Regras de exclusão

- Não capturar tarefas com owner nominal de outra pessoa, exceto se houver follow-up necessário.
- Não capturar comentários gerais de outros participantes sobre suas próprias carteiras.
- Não capturar discussões sem ação definida.

## Regras específicas da função: {{USER_ROLE}}

{{ROLE_RULES}}

## Reuniões a incluir

{{INCLUDE_EVENT_PATTERNS}}

## Reuniões a ignorar

{{EXCLUDE_EVENT_PATTERNS}}

## Schema de saída

Cada tarefa extraída deve ter:

```json
{
  "id": "{{SPRINT_KEY}}-sync-{YYYYMMDD}-{slug}",
  "title": "Ação concreta no infinitivo",
  "context": "Contexto de 1-2 frases",
  "priority": "urgente | normal | recorrente",
  "done": false,
  "source": "Nome da reunião — DD/MM/YYYY",
  "confidence": "alta | média",
  "review_needed": false,
  "source_quote": "frase literal do usuário (apenas Pass 2)",
  "auto_added_at": "ISO now BR"
}
```

## Passes de extração

### Pass 1 — Próximas etapas estruturadas
Buscar seções de "próximas etapas", "action items", "to-dos" com owner = {{USER_DISPLAY_NAME}}. Confidence: alta.

### Pass 2 — Comprometimentos verbais
Buscar frases do próprio usuário: "deixa comigo", "vou ver", "fico de", "me responsabilizo", "eu fecho", "subo isso", "amanhã eu trago". Confidence: média, review_needed: true.
