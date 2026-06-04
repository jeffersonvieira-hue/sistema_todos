---
name: todos-dedup
description: |
  Sub-rotina pós-sync: remove duplicatas em todos-data.json na sprint atual.
  Invocada automaticamente ao final de /todos-sync e na instalação inicial.
trigger:
  sub_routine: todos-sync, atualiza-todos, todos-installer
---

# /todos-dedup — Desduplicação de tasks

## Quando rodar

- **Sempre** após `/todos-sync` concluir com sucesso
- Após instalação inicial (Fase C do installer)
- Manualmente se usuário reportar tasks repetidas

## Paths (dinâmicos)

```
Read: People/{Nome}/.todos/user-config.json → paths.base_dir
DATA = People/{Nome}/todos-data.json
LOG  = People/{Nome}/.todos/change-log.jsonl
```

---

## Algoritmo

1. Carregar `todos-data.json` → sprint `meta.currentSprint`
2. Para cada categoria em `sprints[current].categories[]`:
3. Agrupar items por título normalizado:

```python
def norm_title(t):
    # lower, sem acento, colapsar espaços
```

4. Em cada grupo com 2+ items:
   - **Nunca** merge se qualquer item tem `source` contendo `"Manual"`
   - Escolher **keeper**: item com `context` mais longo; empate → mais antigo (`auto_added_at`)
   - **Merge** nos demais:
     - Concatenar `context` se diferente
     - Unir `source` únicos com ` | `
     - `review_needed = true` se qualquer duplicata tinha
     - Manter maior `priority` (urgente > normal > recorrente)
   - Remover duplicatas do array
5. Append log:

```json
{"timestamp":"...","operation":"todos-dedup","sprint":"S23","groups_merged":3,"items_removed":5}
```

6. Salvar `todos-data.json`
7. Regenerar dashboard:

```bash
python3 "People/{Nome}/generate_dashboard.py"
```

---

## Limiar

- Similaridade de título **> 0.85** (fuzzy) OU título normalizado idêntico
- Mesma sprint, mesma categoria

---

## Report

```
[/todos-dedup] ✅ {N} grupos mergeados, {M} items removidos
```
