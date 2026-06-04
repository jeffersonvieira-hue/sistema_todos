#!/usr/bin/env bash
# Rode após git clone ou git pull para lembrar o próximo passo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Sistema de To-Dos — pós clone/pull"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Próximo passo no Claude Code:"
echo ""
echo "  /todos-installer"
echo ""
echo "A skill instala sua pasta em People/{Nome}/, mapeia Ekyte + Cockpit"
echo "e roda o primeiro sync."
echo ""
echo "Skills locais (1ª vez):"
echo "  for s in todos-installer todos-sync atualiza-todos todos-dedup; do"
echo "    mkdir -p ~/.claude/skills/\$s"
echo "    cp \"Sistema de to do/skills/\$s/SKILL.md\" ~/.claude/skills/\$s/SKILL.md"
echo "  done"
echo ""
echo "Guia: Sistema de to do/GUIA-INSTALACAO-TIME.md"
echo ""
