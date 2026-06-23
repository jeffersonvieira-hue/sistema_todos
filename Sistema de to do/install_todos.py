#!/usr/bin/env python3
"""
install_todos.py — Instalador do Sistema de To-Dos Operacionais V2

Uso:
    python3 "Sistema de to do/install_todos.py"
    python3 "Sistema de to do/install_todos.py" --name "Ana Souza" --email "ana@v4company.com" --role "gestor-trafego"

Flags opcionais:
    --name       Nome completo do usuário
    --email      E-mail V4 do usuário
    --role       Função (coordenador | gestor-projetos | gestor-trafego | copywriter |
                         designer | social-media | dados-bi | atendimento-crm | outro)
    --display    Nome curto de exibição (padrão: primeiro nome)
    --bu         Unidade/BU
    --squad      Squad
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
PEOPLE_DIR = BASE_DIR / "People"
GENERATOR_SOURCE = TEMPLATES_DIR / "base" / "generate_dashboard.py"
AUTO_SYNC_SOURCE = TEMPLATES_DIR / "base" / "auto_sync.py"
OAUTH_SOURCE = TEMPLATES_DIR / "base" / "setup_google_oauth.py"

VALID_ROLES = [
    "coordenador",
    "gestor-projetos",
    "gestor-trafego",
    "copywriter",
    "designer",
    "social-media",
    "dados-bi",
    "atendimento-crm",
    "outro",
]

ROLE_LABELS = {
    "coordenador": "Coordenador",
    "gestor-projetos": "Gestor de Projetos",
    "gestor-trafego": "Gestor de Tráfego",
    "copywriter": "Copywriter",
    "designer": "Designer",
    "social-media": "Social Media",
    "dados-bi": "BI / Dados",
    "atendimento-crm": "Atendimento / CRM",
    "outro": "Outro",
}


def ask(prompt: str, default: str = "") -> str:
    if default:
        value = input(f"{prompt} [{default}]: ").strip()
        return value if value else default
    while True:
        value = input(f"{prompt}: ").strip()
        if value:
            return value
        print("  ⚠️  Campo obrigatório.")


def ask_choice(prompt: str, choices: list[str], default: str = "") -> str:
    print(f"\n{prompt}")
    for i, choice in enumerate(choices, 1):
        marker = " ← padrão" if choice == default else ""
        print(f"  {i}) {choice}{marker}")
    while True:
        raw = input("Escolha (número): ").strip()
        if not raw and default:
            return default
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        print("  ⚠️  Escolha um número válido.")


def ask_bool(prompt: str, default: bool = True) -> bool:
    default_str = "S/n" if default else "s/N"
    raw = input(f"{prompt} [{default_str}]: ").strip().lower()
    if not raw:
        return default
    return raw in ("s", "sim", "y", "yes", "1")


def slugify(value: str) -> str:
    normalized = "".join(c for c in value if c.isalnum() or c in " -_")
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")


def week_number() -> int:
    return datetime.now().isocalendar()[1]


def sprint_key() -> str:
    return f"S{week_number():02d}"


def local_today() -> str:
    return datetime.now().date().isoformat()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_template_json(name: str) -> dict:
    path = TEMPLATES_DIR / name
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def fill_template_str(text: str, vars: dict) -> str:
    for key, value in vars.items():
        text = text.replace(f"{{{{{key}}}}}", str(value))
    return text


def fill_template_json(obj, vars: dict):
    raw = json.dumps(obj, ensure_ascii=False)
    filled = fill_template_str(raw, vars)
    return json.loads(filled)


def load_categories(role: str) -> list[dict]:
    path = TEMPLATES_DIR / "categories" / f"{role}.json"
    if not path.exists():
        path = TEMPLATES_DIR / "categories" / "outro.json"
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data.get("categories", [])


def load_role_config(role: str) -> dict:
    path = TEMPLATES_DIR / "categories" / f"{role}.json"
    if not path.exists():
        path = TEMPLATES_DIR / "categories" / "outro.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


VALID_SYNC_PRESETS = ["yesterday", "last7", "custom"]


def load_template_text(name: str) -> str:
    path = TEMPLATES_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def sync_range_from_preset(preset: str, from_date: str | None = None, to_date: str | None = None) -> tuple[str, str]:
    today = datetime.now().date()
    if preset == "yesterday":
        d = today - timedelta(days=1)
        return d.isoformat(), d.isoformat()
    if preset == "last7":
        start = today - timedelta(days=6)
        return start.isoformat(), today.isoformat()
    if from_date and to_date:
        return from_date, to_date
    return today.isoformat(), today.isoformat()


def collect_sync_range(args: argparse.Namespace, non_interactive: bool) -> dict:
    preset = args.sync_preset
    from_date = args.sync_from
    to_date = args.sync_to

    if args.skip_initial_sync:
        return {"skip": True, "preset": None, "from": None, "to": None}

    if not preset:
        if non_interactive:
            preset = "last7"
        else:
            print("\n─── Primeiro sync (range de reuniões) ───────────────────")
            preset = ask_choice("Período inicial:", VALID_SYNC_PRESETS, "last7")

    if preset == "custom" and not non_interactive and (not from_date or not to_date):
        from_date = ask("Data inicial (YYYY-MM-DD)", (datetime.now().date() - timedelta(days=6)).isoformat())
        to_date = ask("Data final (YYYY-MM-DD)", datetime.now().date().isoformat())
    elif preset == "custom" and non_interactive and (not from_date or not to_date):
        from_date, to_date = sync_range_from_preset("last7")

    if preset != "custom":
        from_date, to_date = sync_range_from_preset(preset, from_date, to_date)

    return {
        "skip": False,
        "preset": preset,
        "from": from_date,
        "to": to_date,
        "force_reprocess": False,
    }


def build_refresh_trigger(sync: dict) -> dict:
    if sync.get("skip"):
        return {}
    return {
        "from": sync["from"],
        "to": sync["to"],
        "force_reprocess": sync.get("force_reprocess", False),
        "preset": sync.get("preset", "custom"),
        "requested_at": now_iso(),
        "source": "install_todos.py",
    }


def build_mapeamento_md(info: dict) -> str:
    tmpl = load_template_text("mapeamento.template.md")
    if not tmpl:
        return f"# Mapeamento — {info['full_name']}\n\nPendente: rodar /todos-installer Fase B.\n"
    vars = {
        "NOW": now_iso(),
        "FULL_NAME": info["full_name"],
        "EMAIL": info["email"],
        "ROLE_LABEL": info["role_label"],
        "BU": info["bu"],
        "SQUAD": info["squad"],
        "DEFAULT_WORKSPACE_ID": info.get("ekyte_workspace") or "null",
        "DEFAULT_TASK_TYPE_ID": "null",
        "WEEK_NUMBER": str(week_number()),
    }
    return fill_template_str(tmpl, vars)


def read_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def validate_mapping(ekyte_config: dict, user_config: dict) -> list[str]:
    issues = []
    workspaces = ekyte_config.get("workspaces") or []
    real_workspaces = [w for w in workspaces if w.get("id") != "__other__" and not w.get("is_other")]
    if not real_workspaces:
        issues.append("ekyte-config.json: workspaces vazio (rode Fase B do /todos-installer)")

    default_ws = ekyte_config.get("default_workspace_id")
    if not default_ws:
        issues.append("ekyte-config.json: default_workspace_id não definido")

    cockpit = user_config.get("cockpit") or {}
    if cockpit.get("enabled") and not (cockpit.get("project_document_ids") or []):
        issues.append("user-config.json: cockpit habilitado mas project_document_ids vazio")

    return issues


def mapping_is_complete(state_dir: Path) -> bool:
    state = read_json(state_dir / "install-state.json", {})
    return state.get("mapping_status") == "complete"


def check_prerequisites() -> list[str]:
    issues = []
    if not GENERATOR_SOURCE.exists():
        issues.append(f"generate_dashboard.py não encontrado em: {GENERATOR_SOURCE}")
    if not AUTO_SYNC_SOURCE.exists():
        issues.append(f"auto_sync.py não encontrado em: {AUTO_SYNC_SOURCE}")
    if not OAUTH_SOURCE.exists():
        issues.append(f"setup_google_oauth.py não encontrado em: {OAUTH_SOURCE}")
    if not TEMPLATES_DIR.exists():
        issues.append(f"Pasta de templates não encontrada: {TEMPLATES_DIR}")
    if sys.version_info < (3, 9):
        issues.append(f"Python 3.9+ necessário (atual: {sys.version})")
    return issues


def collect_user_info(args: argparse.Namespace) -> dict:
    print("\n" + "═" * 60)
    print("  SISTEMA DE TO-DOS OPERACIONAIS V2 — INSTALADOR")
    print("═" * 60)
    print("\nVamos configurar o sistema para o novo usuário.")
    print("Pressione Enter para aceitar o valor padrão.\n")

    non_interactive = args.yes or not sys.stdin.isatty()
    full_name = args.name or ask("Nome completo")
    display_name = args.display or (full_name.split()[0] if non_interactive else ask("Nome curto de exibição", full_name.split()[0]))
    email = args.email or ask("E-mail V4")
    bu = args.bu or ("Invictus" if non_interactive else ask("Unidade / BU", "Invictus"))
    squad = args.squad or (bu if non_interactive else ask("Squad", bu))

    if args.role and args.role in VALID_ROLES:
        role = args.role
    elif non_interactive:
        role = "coordenador"
    else:
        role = ask_choice("Função principal:", VALID_ROLES, "coordenador")

    role_label = args.role_label or ROLE_LABELS.get(role, role)
    custom_role_rules = [
        rule.strip()
        for rule in (args.role_rules or "").split(";")
        if rule.strip()
    ]
    if role == "outro" and not non_interactive:
        role_label = ask("Nome da sua função", role_label)
        raw_rules = input(
            "Responsabilidades que devem virar tarefas (separe por ponto e vírgula): "
        ).strip()
        if raw_rules:
            custom_role_rules = [rule.strip() for rule in raw_rules.split(";") if rule.strip()]

    print(f"\n✅ Identidade confirmada:")
    print(f"   Nome:    {full_name} ({display_name})")
    print(f"   E-mail:  {email}")
    print(f"   Função:  {role_label}")
    print(f"   BU:      {bu} / {squad}")

    if non_interactive:
        use_calendar = True
        use_drive = True
        use_ekyte = True
        use_cockpit = (role == "coordenador")
        ekyte_workspace = None
        print("\n─── Integrações (modo automático) ───────────────────────")
        print(f"  Calendar: {'✓' if use_calendar else '–'}  Drive: {'✓' if use_drive else '–'}  Ekyte: {'✓' if use_ekyte else '–'}  Cockpit: {'✓' if use_cockpit else '–'}")
    else:
        print("\n─── Integrações ────────────────────────────────────────")
        use_calendar = ask_bool("Usar Google Calendar?", True)
        use_drive = ask_bool("Usar Google Drive para transcrições?", True)
        use_ekyte = ask_bool("Usar Ekyte?", True)
        use_cockpit = ask_bool("Usar Cockpit (alertas de projetos)?", role == "coordenador")
        ekyte_workspace = None
        if use_ekyte:
            print("\n─── Ekyte ──────────────────────────────────────────────")
            print("  (Deixe em branco para configurar depois via ekyte-config.json)")
            ekyte_workspace = input("  Workspace ID padrão: ").strip() or None

    return {
        "full_name": full_name,
        "display_name": display_name,
        "email": email,
        "role": role,
        "role_label": role_label,
        "custom_role_rules": custom_role_rules,
        "bu": bu,
        "squad": squad,
        "use_calendar": use_calendar,
        "use_drive": use_drive,
        "use_ekyte": use_ekyte,
        "use_cockpit": use_cockpit,
        "ekyte_workspace": ekyte_workspace,
        "non_interactive": non_interactive,
        "skip_mapping": args.skip_mapping,
        "skip_initial_sync": args.skip_initial_sync,
        "sync_range": collect_sync_range(args, non_interactive),
    }


def build_user_config(info: dict) -> dict:
    role_cfg = load_role_config(info["role"])
    categories = [c["id"] for c in load_categories(info["role"])]
    role_rules = list(role_cfg.get("extraction_rules", []))
    role_rules.extend(info.get("custom_role_rules", []))

    return {
        "schema_version": "2.0",
        "user": {
            "full_name": info["full_name"],
            "display_name": info["display_name"],
            "email": info["email"],
            "role": info["role"],
            "role_label": info["role_label"],
            "bu": info["bu"],
            "squad": info["squad"],
        },
        "paths": {
            "base_dir": f"People/{info['full_name']}",
            "dashboard_html": "todos-dashboard.html",
            "todos_data": "todos-data.json",
            "state_dir": ".todos",
        },
        "calendar": {
            "enabled": info["use_calendar"],
            "timezone": "America/Sao_Paulo",
            "include_event_patterns": [],
            "exclude_event_patterns": [],
            "capture_team_wide_tasks": True,
        },
        "extraction": {
            "owner_names": [info["full_name"], info["display_name"]],
            "owner_aliases": [],
            "capture_direct_assignments": True,
            "capture_follow_ups": True,
            "capture_role_responsibilities": True,
            "ignore_other_people_tasks": True,
            "role_rules": role_rules,
        },
        "dashboard": {
            "title": f"Todos — {info['full_name']}",
            "categories": categories,
            "hide_done_by_default": False,
            "history_enabled": True,
            "follow_enabled": True,
        },
        "ekyte": {
            "enabled": info["use_ekyte"],
            "direct_create_enabled": info["use_ekyte"],
            "default_workspace_id": info.get("ekyte_workspace"),
            "default_project_id": None,
            "default_task_type_id": None,
            "default_assignee_email": info["email"],
            "planned_task_default": True,
            "default_due_days": 2,
            "required_tags": {"routine": True, "week": True},
        },
        "cockpit": {
            "enabled": info["use_cockpit"],
            "project_document_ids": [],
            "ticker_filter": [],
        },
    }


def build_todos_data(info: dict) -> dict:
    categories = load_categories(info["role"])
    sprint = sprint_key()
    return {
        "meta": {
            "owner": info["full_name"],
            "currentSprint": sprint,
            "lastUpdated": local_today(),
        },
        "sprints": {
            sprint: {
                "categories": [
                    {"id": c["id"], "name": c["name"], "color": c["color"], "items": []}
                    for c in categories
                ]
            }
        },
    }


def build_ekyte_config(info: dict) -> dict:
    tmpl = load_template_json("ekyte-config.template.json")
    vars = {
        "NOW": now_iso(),
        "EMAIL": info["email"],
        "FULL_NAME": info["full_name"],
        "ROLE_LABEL": info["role_label"],
    }
    return fill_template_json(tmpl, vars)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def install(info: dict) -> Path:
    user_dir = PEOPLE_DIR / info["full_name"]
    state_dir = user_dir / ".todos"

    print(f"\n─── Instalando em {user_dir} ────────────────────────────")

    if user_dir.exists():
        if info.get("non_interactive"):
            print("  Diretório já existe; modo --yes: preservando dados e atualizando config.")
        else:
            print(f"  ⚠️  Diretório já existe: {user_dir}")
            if not ask_bool(
                "  Sobrescrever arquivos de configuração? (dados existentes serão preservados)",
                False,
            ):
                print("  Instalação cancelada.")
                sys.exit(0)

    PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
    user_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy runtime scripts
    dest_generator = user_dir / "generate_dashboard.py"
    shutil.copy2(GENERATOR_SOURCE, dest_generator)
    print(f"  ✓ generate_dashboard.py copiado")
    shutil.copy2(AUTO_SYNC_SOURCE, user_dir / "auto_sync.py")
    print(f"  ✓ auto_sync.py copiado")
    shutil.copy2(OAUTH_SOURCE, user_dir / "setup_google_oauth.py")
    print(f"  ✓ setup_google_oauth.py copiado")

    # 2. todos-data.json (only if not exists)
    todos_data_path = user_dir / "todos-data.json"
    if not todos_data_path.exists():
        write_json(todos_data_path, build_todos_data(info))
        print(f"  ✓ todos-data.json criado ({sprint_key()})")
    else:
        print(f"  – todos-data.json já existe, preservado")

    # 3. user-config.json
    write_json(state_dir / "user-config.json", build_user_config(info))
    print(f"  ✓ .todos/user-config.json criado")

    # 4. ekyte-config.json (only if not exists)
    ekyte_config_path = state_dir / "ekyte-config.json"
    if not ekyte_config_path.exists():
        write_json(ekyte_config_path, build_ekyte_config(info))
        print(f"  ✓ .todos/ekyte-config.json criado")
    else:
        print(f"  – .todos/ekyte-config.json já existe, preservado")

    # 5. Empty state files + install state
    existing_state = read_json(state_dir / "install-state.json", {})
    mapping_status = existing_state.get("mapping_status", "pending")
    install_state = {
        "installed_at": existing_state.get("installed_at") or now_iso(),
        "updated_at": now_iso(),
        "version": "2.1",
        "user": info["full_name"],
        "role": info["role"],
        "mapping_status": mapping_status,
        "bu": info["bu"],
        "squad": info["squad"],
    }
    empty_files = {
        "last-sync.json": {},
        "last-alerts.json": {"active_alerts": {}, "resolved_alerts_24h": {}},
        "ekyte-pending.json": [],
        "ekyte-errors.json": [],
        "refresh-errors.json": [],
    }
    for filename, content in empty_files.items():
        path = state_dir / filename
        if not path.exists():
            write_json(path, content)

    write_json(state_dir / "install-state.json", install_state)

    # 5b. Mapeamento skeleton (somente se não existir)
    mapeamento_path = state_dir / "mapeamento.md"
    if not mapeamento_path.exists():
        mapeamento_path.write_text(build_mapeamento_md(info), encoding="utf-8")
        print(f"  ✓ .todos/mapeamento.md criado")
    else:
        print(f"  – .todos/mapeamento.md já existe, preservado")

    # 5c. Refresh trigger para primeiro sync (somente se não existir)
    sync = info.get("sync_range") or {}
    trigger_path = state_dir / "refresh-trigger.json"
    if not sync.get("skip") and not trigger_path.exists():
        trigger = build_refresh_trigger(sync)
        write_json(trigger_path, trigger)
        print(f"  ✓ .todos/refresh-trigger.json ({trigger['from']} → {trigger['to']}, preset: {trigger['preset']})")
    elif sync.get("skip"):
        print(f"  – refresh-trigger omitido (--skip-initial-sync)")
    else:
        print(f"  – .todos/refresh-trigger.json já existe, preservado")

    print(f"  ✓ arquivos de estado inicializados (mapping_status={mapping_status})")

    # 6. Generate dashboard
    print(f"\n─── Gerando dashboard inicial ──────────────────────────")
    import subprocess
    result = subprocess.run(
        [sys.executable, str(dest_generator), "--validate"],
        capture_output=True, text=True, cwd=str(BASE_DIR)
    )
    if result.returncode != 0:
        print(f"  ⚠️  Validação falhou:\n{result.stderr}")
    else:
        result2 = subprocess.run(
            [sys.executable, str(dest_generator)],
            capture_output=True, text=True, cwd=str(BASE_DIR)
        )
        if result2.returncode == 0:
            print(f"  ✓ {result2.stdout.strip()}")
        else:
            print(f"  ⚠️  Geração falhou: {result2.stderr}")

    return user_dir, state_dir


def print_next_steps(info: dict, user_dir: Path, mapping_issues: list[str] | None = None) -> None:
    print("\n" + "═" * 60)
    print("  ✅ INSTALAÇÃO CONCLUÍDA")
    print("═" * 60)
    print(f"""
Usuário:  {info['full_name']} ({info['role_label']})
Diretório: {user_dir}

PRÓXIMOS PASSOS:

1. Abrir o dashboard:
   open "{user_dir}/todos-dashboard.html"

2. Subir o servidor local (para criar tasks no Ekyte):
   python3 "{user_dir}/generate_dashboard.py" --serve

3. Ativar atualização automática a cada 2 horas (segunda a sexta):
   python3 "Sistema de to do/install_automation.py" --name "{info['full_name']}"

4. Se ainda não configurou o MCP, copie:
   cp "Sistema de to do/templates/mcp.example.json" ~/.claude/mcp.json
   (edite com seus tokens reais)

5. Configurar Ekyte (se habilitado):
   Edite: {user_dir}/.todos/ekyte-config.json
   Preencha: workspaces, projetos e tipos de task reais.

6. Mapeamento Ekyte + Cockpit (obrigatório na 1ª vez):
   /todos-installer
   (Fase B: busca workspaces, projetos e time no MCP)

7. Primeiro sync de reuniões (usa o range gravado em refresh-trigger.json):
   /atualiza-todos
""")
    if mapping_issues:
        print("\n⚠️  Mapeamento incompleto:")
        for issue in mapping_issues:
            print(f"   - {issue}")
        print("\n   Rode /todos-installer (Fase B) antes de usar Ekyte ou Cockpit.\n")
    if not info.get("use_ekyte"):
        print("  ℹ️  Ekyte desabilitado. Para habilitar depois, edite user-config.json.")
    if not info.get("use_cockpit"):
        print("  ℹ️  Cockpit desabilitado. Para alertas de projeto, edite user-config.json.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Instala o Sistema de To-Dos Operacionais V2")
    parser.add_argument("--name", help="Nome completo do usuário")
    parser.add_argument("--email", help="E-mail V4 do usuário")
    parser.add_argument("--role", choices=VALID_ROLES, help="Função do usuário")
    parser.add_argument("--role-label", help="Nome da função quando --role=outro")
    parser.add_argument(
        "--role-rules",
        help="Responsabilidades específicas separadas por ponto e vírgula",
    )
    parser.add_argument("--display", help="Nome curto de exibição")
    parser.add_argument("--bu", help="Unidade/BU")
    parser.add_argument("--squad", help="Squad")
    parser.add_argument("--yes", "-y", action="store_true", help="Modo não-interativo: aceitar todos os padrões")
    parser.add_argument(
        "--sync-preset",
        choices=VALID_SYNC_PRESETS,
        help="Preset do primeiro sync: yesterday, last7 ou custom",
    )
    parser.add_argument("--sync-from", help="Data inicial do primeiro sync (YYYY-MM-DD)")
    parser.add_argument("--sync-to", help="Data final do primeiro sync (YYYY-MM-DD)")
    parser.add_argument("--skip-mapping", action="store_true", help="Não validar mapeamento ao final")
    parser.add_argument("--skip-initial-sync", action="store_true", help="Não gravar refresh-trigger.json")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    issues = check_prerequisites()
    if issues:
        print("❌ Pré-requisitos não atendidos:")
        for issue in issues:
            print(f"   - {issue}")
        return 1

    try:
        info = collect_user_info(args)
        user_dir, state_dir = install(info)

        ekyte_cfg = read_json(state_dir / "ekyte-config.json", {})
        user_cfg = read_json(state_dir / "user-config.json", {})
        mapping_issues = [] if info.get("skip_mapping") else validate_mapping(ekyte_cfg, user_cfg)

        print_next_steps(info, user_dir, mapping_issues)

        if mapping_issues and not info.get("skip_mapping"):
            return 2
        return 0
    except KeyboardInterrupt:
        print("\n\nInstalação cancelada pelo usuário.")
        return 1
    except Exception as exc:
        print(f"\n❌ Erro na instalação: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
