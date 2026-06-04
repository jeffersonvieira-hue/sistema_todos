# sistema_todos

Sistema de To-Dos Operacionais V2 — Colli&Co / V4.

Documentação completa: [`Sistema de to do/README.md`](Sistema%20de%20to%20do/README.md)

---

## Acabou de clonar ou deu `git pull`?

**Próximo passo obrigatório no Claude Code:**

```
/todos-installer
```

A skill guia a instalação completa (mapeamento Ekyte + Cockpit, dashboard e primeiro sync).

### Antes da skill (só na 1ª vez)

```bash
cp "Sistema de to do/templates/mcp.example.json" mcp.json
# editar tokens no mcp.json — não commitar

# copiar skills para o Claude Code
for s in todos-installer todos-sync atualiza-todos todos-dedup; do
  mkdir -p ~/.claude/skills/$s
  cp "Sistema de to do/skills/$s/SKILL.md" ~/.claude/skills/$s/SKILL.md
done
```

Depois abra o Claude Code na pasta do repo e rode **`/todos-installer`**.

Script de lembrete no terminal:

```bash
bash "Sistema de to do/scripts/pos-pull.sh"
```

---

## Clone

```bash
git clone https://github.com/jeffersonvieira-hue/sistema_todos.git
cd sistema_todos
```

Em seguida: **`/todos-installer`** no Claude Code.
