#!/usr/bin/env python3
"""Install the local dashboard and two-hour automatic sync on macOS."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parent.parent
PEOPLE_DIR = REPO_DIR / "People"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support"


def slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")


def copy_runtime(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / ".todos").mkdir(parents=True, exist_ok=True)
    for filename in ("generate_dashboard.py", "auto_sync.py", "setup_google_oauth.py"):
        shutil.copy2(source / filename, target / filename)
    repo_mcp = REPO_DIR / "mcp.json"
    if repo_mcp.exists():
        shutil.copy2(repo_mcp, target / "mcp.json")
    if not (target / "todos-data.json").exists():
        shutil.copy2(source / "todos-data.json", target / "todos-data.json")
    source_state = source / ".todos"
    for filename in ("user-config.json", "ekyte-config.json", "install-state.json"):
        source_file = source_state / filename
        target_file = target / ".todos" / filename
        if source_file.exists() and not target_file.exists():
            shutil.copy2(source_file, target_file)


def plist_payload(label: str, arguments: list[str], working_dir: Path, stdout: Path, stderr: Path, interval: int | None = None) -> dict:
    payload = {
        "Label": label,
        "ProgramArguments": arguments,
        "WorkingDirectory": str(working_dir),
        "ProcessType": "Background",
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        "StandardOutPath": str(stdout),
        "StandardErrorPath": str(stderr),
    }
    if interval:
        payload["StartInterval"] = interval
        payload["RunAtLoad"] = False
    else:
        payload["RunAtLoad"] = True
        payload["KeepAlive"] = True
    return payload


def write_plist(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=False)
    path.chmod(0o600)


def reload_agent(label: str, plist_path: Path) -> None:
    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootout", f"{domain}/{label}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(["launchctl", "bootstrap", domain, str(plist_path)], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ativa dashboard e sync automático no macOS")
    parser.add_argument("--name", required=True, help="Nome usado em People/{Nome}")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--interval", type=int, default=7200, help="Intervalo em segundos")
    args = parser.parse_args()

    source = PEOPLE_DIR / args.name
    if not source.exists():
        raise SystemExit(f"Usuário não instalado: {source}")

    config_path = source / ".todos" / "user-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    display_name = config.get("user", {}).get("display_name") or args.name.split()[0]
    runtime = APP_SUPPORT_DIR / f"Todos {display_name}"
    copy_runtime(source, runtime)

    identifier = slug(args.name)
    dashboard_label = f"com.v4.todos-dashboard.{identifier}"
    sync_label = f"com.v4.todos-auto-sync.{identifier}"
    dashboard_plist = LAUNCH_AGENTS_DIR / f"{dashboard_label}.plist"
    sync_plist = LAUNCH_AGENTS_DIR / f"{sync_label}.plist"
    state = runtime / ".todos"

    write_plist(
        dashboard_plist,
        plist_payload(
            dashboard_label,
            [
                sys.executable,
                str(runtime / "generate_dashboard.py"),
                "--serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.port),
                "--keep-transcripts",
            ],
            runtime,
            state / "dashboard-server.log",
            state / "dashboard-server.err.log",
        ),
    )
    write_plist(
        sync_plist,
        plist_payload(
            sync_label,
            [
                sys.executable,
                str(runtime / "auto_sync.py"),
                "--lookback-days",
                "2",
                "--max-files",
                "5",
                "--weekdays-only",
            ],
            runtime,
            state / "auto-sync-launchd.log",
            state / "auto-sync-launchd.err.log",
            interval=args.interval,
        ),
    )
    reload_agent(dashboard_label, dashboard_plist)
    reload_agent(sync_label, sync_plist)

    print(f"OK: runtime em {runtime}")
    print(f"Dashboard: http://127.0.0.1:{args.port}/")
    print(f"Sync: a cada {args.interval // 60} minutos, somente segunda a sexta")
    print(f"OAuth: python3 \"{runtime / 'setup_google_oauth.py'}\"")
    print("Gemini: salve GEMINI_API_KEY em ~/.config/todos-auto-sync/secrets.env")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
