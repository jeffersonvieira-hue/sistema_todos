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
1. Ler as transcrições das suas reuniões (range do `refresh-trigger.json` ou padrão)
2. Extrair tasks com seu nome como owner
3. **Desduplicar** automaticamente (`todos-dedup` após cada sync)
4. Criar alertas de projetos (se Cockpit habilitado)
5. Regenerar o dashboard

---

## Abrir o dashboard

```bash
open "People/{Seu Nome}/todos-dashboard.html"
python3 "People/{Seu Nome}/generate_dashboard.py" --serve
```

Acesse: `http://127.0.0.1:8787` (servidor local necessário para Ekyte gravar em disco).

---

## Concluir uma task

1. Clique no checkbox da task
2. O modal de conclusão abre
3. Opções: **Cancelar**, **Concluir sem nota**, **Concluir** (com anotação)
4. Marque **Follow** se quiser acompanhar depois de concluída

**Esc** ou clicar fora = Cancelar (não conclui).

---

## Usar o Follow

Tasks em Follow aparecem no chip **Follow**.

**Concluir follow:** clique em **Concluir follow** na aba Follow para remover do radar. Opcionalmente adicione nota final (vai para o histórico da task).

---

## Ver histórico

Clique no chip **Histórico**. Mostra tasks concluídas por mês, com fonte, data e anotações.

---

## Adicionar task manualmente

Clique em **+ Task** no topo do dashboard.

---

## Subir task para o Ekyte

Clique em **↑ Ekyte** no card. Use **Outros (informar ID)** se workspace/projeto não estiver listado.

---

## Filtros e busca

Chips: Todos, Abertos, Urgentes, Verificar, Alertas, Follow, Histórico.

Busca por título, contexto, fonte ou anotação.
