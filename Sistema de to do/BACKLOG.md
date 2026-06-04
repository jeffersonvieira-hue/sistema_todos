# Backlog e Riscos Conhecidos

## Prioridade alta

### 1. Consumidor real de `refresh-trigger.json`

Hoje o botão Atualizar grava o trigger, mas não executa sozinho o Pipeline A/B.

Implementar um watcher/runner que:

1. detecta `.todos/refresh-trigger.json`;
2. lê período e `force_reprocess`;
3. roda Calendar + Drive;
4. processa transcrições;
5. roda alertas do Cockpit;
6. regenera dashboard;
7. grava sucesso/erro;
8. apaga ou arquiva o trigger.

### 2. Codificar extração de to-dos como script/skill versionado

Hoje a regra de extração ainda depende das skills em `~/.claude/skills` e da leitura do agente.

Criar script/skill dentro do repo para:

- receber um transcript `.txt`;
- aplicar prompt de extração;
- retornar JSON de itens candidatos;
- marcar confiança e `review_needed`;
- sugerir categoria.

### 3. Resolver divergência entre skills antigas

Há conflito entre:

- `todos-sync`: erro de Drive deve logar e continuar;
- `atualiza-todos`: erro de Drive deve pausar.

Decidir uma regra única. Sugestão:

- erro em uma transcrição específica: loga e continua;
- falha global de autenticação/Drive: pausa e mostra erro no dashboard.

## Prioridade média

### 4. Processamento real da fila Ekyte

Hoje o dashboard grava `.todos/ekyte-pending.json` quando servido localmente. Sem servidor, ele baixa o JSON atualizado e copia o conteúdo para o clipboard.

Falta automatizar:

- leitura da fila;
- criação real no Ekyte;
- gravação de `ekaite_task_id`;
- atualização do dashboard;
- tratamento de falhas por item.

### 5. Testes automatizados

Adicionar testes simples para:

- schema válido;
- ids duplicados;
- prioridades inválidas;
- HTML com JS válido;
- endpoints `/api/refresh` e `/api/ekyte-queue`.

### 6. Separar dados sensíveis de operação

Documentar melhor os caminhos de token sem expor segredo.

Garantir que nenhum arquivo de credencial entre em git.

## Prioridade baixa

### 7. Melhor UX do dashboard

Possíveis melhorias:

- botão para mostrar só `review_needed`;
- agrupamento por projeto/cliente;
- ordenação por urgência e horário de origem;
- destaque de itens Ekyte elegíveis;
- botão "copiar resumo do dia";
- modo impressão.

### 8. Rotação de sprint

Criar/portar rotina `todos-rotate` para:

- arquivar sprint;
- calcular taxa de conclusão;
- carregar pendentes;
- resetar recorrentes;
- criar nova sprint.

### 9. Integração de alertas Cockpit versionada no repo

Pipeline B ainda depende fortemente das skills externas.

Trazer o mapa de sinais para um arquivo versionado ou documentar com precisão como reconstituir.
