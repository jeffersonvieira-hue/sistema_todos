# Guia de Uso Diário — Sistema de To-Dos Operacionais V2

## Rotina sugerida

| Momento | Ação |
|---|---|
| Manhã | Abrir dashboard → revisar backlog do dia |
| Após reunião | `/atualiza-todos` → novos todos criados automaticamente |
| Ao longo do dia | Concluir tasks, adicionar anotações, marcar Follow |
| Fim do dia | Revisar Histórico, subir Ekyte |

---

## Atualizar to-dos (após reuniões)

No Claude Code:

```
/atualiza-todos
```

O sistema vai:
1. Ler as transcrições das suas reuniões de ontem (ou do período configurado)
2. Extrair tasks com seu nome como owner
3. Criar alertas de projetos com score crítico (se Cockpit habilitado)
4. Atualizar o dashboard automaticamente

---

## Abrir o dashboard

```bash
# Arquivo estático (rápido, sem Ekyte)
open "People/{Seu Nome}/todos-dashboard.html"

# Com servidor local (para criar tasks no Ekyte)
python3 "People/{Seu Nome}/generate_dashboard.py" --serve
# Acesse: http://127.0.0.1:8787
```

---

## Concluir uma task

1. Clique no checkbox da task
2. O modal de conclusão abre
3. Opções:
   - **Cancelar** — fecha sem concluir
   - **Concluir sem nota** — conclui direto
   - **Concluir** — salva uma anotação antes de concluir
4. Marque **Follow** se quiser acompanhar depois de concluída

**Esc** ou clicar fora do modal = Cancelar (não conclui).

---

## Usar o Follow

Tasks marcadas como Follow aparecem na aba **Follow** do dashboard.

Use para tasks que:
- Dependem de outra pessoa
- Você quer checar resultado depois
- São decisões que merecem acompanhamento

---

## Ver histórico

Clique no chip **Histórico** no dashboard.

Mostra todas as tasks concluídas, agrupadas por mês, com:
- Título e categoria original
- Fonte (qual reunião gerou)
- Data de conclusão
- Anotação, se houver

---

## Adicionar task manualmente

No dashboard, clique em **+ Task** no topo.

Preencha:
- Categoria
- Título
- Prioridade e Confiança
- Contexto (opcional)
- Fonte (opcional)

---

## Subir task para o Ekyte

No card da task, clique em **↑ Ekyte**.

O sistema vai:
1. Criar a task no Ekyte com seu workspace, projeto e tipo configurados
2. Marcar a task no dashboard como `✓ Ekyte #ID`
3. Abrir o link direto para a task no Ekyte

Se o servidor local não estiver rodando, o sistema salva na fila e você pode processar depois com `/todos-promote-ekaite`.

---

## Filtros do dashboard

| Chip / Card | O que mostra |
|---|---|
| **Todos** | Todos os itens da sprint |
| **Abertos** | Só tasks não concluídas |
| **Urgentes** | Tasks com prioridade urgente |
| **Verificar** | Tasks marcadas `review_needed` |
| **Alertas** | Alertas críticos de projetos |
| **Follow** | Tasks marcadas para acompanhamento |
| **Histórico** | Todas as tasks concluídas |

Clique em qualquer categoria no chip de categorias para filtrar por cliente/área.

---

## Busca

Use a barra de busca no topo para encontrar tasks por:
- Título
- Contexto
- Fonte (nome da reunião)
- Anotação de conclusão
