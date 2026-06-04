#!/usr/bin/env python3
"""
Generate and optionally serve Jefferson Vieira's personal todos dashboard.

The JSON file is the source of truth. This script validates it before writing
the self-contained HTML dashboard, so Pipeline A/B can call one stable command
instead of pasting inline Python blocks.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import posixpath
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None


BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR.parents[1]
DATA_PATH = BASE_DIR / "todos-data.json"
HTML_PATH = BASE_DIR / "todos-dashboard.html"
STATE_DIR = BASE_DIR / ".todos"
ARCHIVE_DIR = STATE_DIR / "archive"
TRANSCRIPTS_DIR = STATE_DIR / "transcripts"
TRIGGER_PATH = STATE_DIR / "refresh-trigger.json"
ERRORS_PATH = STATE_DIR / "refresh-errors.json"
LAST_SYNC_PATH = STATE_DIR / "last-sync.json"
LAST_ALERTS_PATH = STATE_DIR / "last-alerts.json"
EKYTE_PENDING_PATH = STATE_DIR / "ekyte-pending.json"
EKYTE_CONFIG_PATH = STATE_DIR / "ekyte-config.json"
EKYTE_ERRORS_PATH = STATE_DIR / "ekyte-errors.json"
USER_CONFIG_PATH = STATE_DIR / "user-config.json"

_user_config_cache: Optional[Dict[str, Any]] = None


def load_user_config() -> Dict[str, Any]:
    """Load user-config.json. Returns {} if not found (V1 backward compat)."""
    global _user_config_cache
    if _user_config_cache is not None:
        return _user_config_cache
    raw = read_json(USER_CONFIG_PATH, {})
    _user_config_cache = raw if isinstance(raw, dict) else {}
    return _user_config_cache


def user_default_email() -> str:
    cfg = load_user_config()
    return (
        cfg.get("user", {}).get("email")
        or cfg.get("ekyte", {}).get("default_assignee_email")
        or "jefferson.vieira@v4company.com"
    )


def user_full_name() -> str:
    cfg = load_user_config()
    return cfg.get("user", {}).get("full_name") or "Jefferson Vieira"


def user_workspace_label() -> str:
    cfg = load_user_config()
    user = cfg.get("user", {})
    name = user.get("full_name") or ""
    role = user.get("role", "")
    if name:
        return f"Coord. {name}" if "coord" in role.lower() else name
    return "Coord. Jefferson Vieira"
CLEANUP_LOG_PATH = STATE_DIR / "cleanup-log.jsonl"
MCP_CONFIG_PATH = REPO_DIR / "mcp.json"
VALID_PRIORITIES = {"urgente", "normal", "recorrente"}
VALID_CONFIDENCES = {"alta", "média", "media", "baixa"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ROUTINE_TAG_NAMES = [
    "AÇÃO GERENCIAL",
    "SPRINT GROWTH",
    "WEEKLY EXPANSÃO",
    "ALINHAMENTO COMITÊ",
    "QUALITY CONTROL",
    "WAR",
]
WEEK_TAG_NAMES = [f"SEMANA {week:02d}" for week in range(1, 53)]
KEEP_TRANSCRIPTS = False


def now_br() -> str:
    if ZoneInfo:
        return datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds")
    return datetime.now().isoformat(timespec="seconds")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def read_json_list(path: Path) -> List[Any]:
    payload = read_json(path, [])
    return payload if isinstance(payload, list) else []


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp_path, path)


def write_text_atomic(path: Path, payload: str) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        fh.write(payload)
    os.replace(tmp_path, path)


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def cleanup_transcripts(quiet: bool = False) -> Tuple[int, int]:
    if not TRANSCRIPTS_DIR.exists():
        return 0, 0
    removed_count = 0
    removed_bytes = 0
    for path in TRANSCRIPTS_DIR.iterdir():
        if not path.is_file():
            continue
        size = path.stat().st_size
        path.unlink()
        removed_count += 1
        removed_bytes += size
    if removed_count:
        append_jsonl(
            CLEANUP_LOG_PATH,
            {
                "timestamp": now_br(),
                "operation": "cleanup-transcripts-after-dashboard-generate",
                "directory": str(TRANSCRIPTS_DIR),
                "files_removed": removed_count,
                "bytes_removed": removed_bytes,
            },
        )
        if not quiet:
            print(
                f"Cleaned {removed_count} transcript files from {TRANSCRIPTS_DIR} "
                f"({removed_bytes / 1024 / 1024:.2f} MB)"
            )
    return removed_count, removed_bytes


def validate_date(value: str, label: str) -> None:
    if not isinstance(value, str) or not DATE_RE.match(value):
        raise ValueError(f"{label} must use YYYY-MM-DD")
    datetime.strptime(value, "%Y-%m-%d")


def local_today() -> str:
    if ZoneInfo:
        return datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    return datetime.now().date().isoformat()


def slugify(value: str, max_length: int = 64) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return (slug[:max_length].strip("-") or "task")


def iter_items(data: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    current_sprint = data.get("meta", {}).get("currentSprint")
    sprint = data.get("sprints", {}).get(current_sprint, {})
    for category in sprint.get("categories", []) or []:
        for item in category.get("items", []) or []:
            yield category.get("id", ""), category, item


def find_current_item(data: Dict[str, Any], item_id: str) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    for category_id, category, item in iter_items(data):
        if item.get("id") == item_id:
            return category_id, category, item
    raise ValueError(f"Item not found: {item_id}")


def find_current_category(data: Dict[str, Any], category_id: str) -> Dict[str, Any]:
    current_sprint = data.get("meta", {}).get("currentSprint")
    sprint = data.get("sprints", {}).get(current_sprint, {})
    for category in sprint.get("categories", []) or []:
        if category.get("id") == category_id:
            return category
    raise ValueError(f"Category not found: {category_id}")


def unique_manual_item_id(data: Dict[str, Any], title: str) -> str:
    sprint_key = str(data.get("meta", {}).get("currentSprint") or "sprint").lower()
    base = f"{sprint_key}-manual-{local_today().replace('-', '')}-{slugify(title)}"
    existing = {item.get("id") for _category_id, _category, item in iter_items(data)}
    if base not in existing:
        return base
    counter = 2
    while f"{base}-{counter}" in existing:
        counter += 1
    return f"{base}-{counter}"


def validate_data(data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(data, dict):
        return ["todos-data.json must be a JSON object"], warnings

    meta = data.get("meta")
    if not isinstance(meta, dict):
        errors.append("Missing object: meta")
        return errors, warnings

    current_sprint = meta.get("currentSprint")
    if not current_sprint:
        errors.append("Missing field: meta.currentSprint")

    sprints = data.get("sprints")
    if not isinstance(sprints, dict):
        errors.append("Missing object: sprints")
        return errors, warnings

    sprint = sprints.get(current_sprint)
    if not isinstance(sprint, dict):
        errors.append(f"Current sprint '{current_sprint}' not found in sprints")
        return errors, warnings

    categories = sprint.get("categories")
    if not isinstance(categories, list):
        errors.append(f"sprints.{current_sprint}.categories must be a list")
        return errors, warnings

    seen_ids = set()
    required_item_fields = {"id", "title", "priority", "done", "source"}
    for category in categories:
        if not isinstance(category, dict):
            errors.append("Category entries must be objects")
            continue
        category_id = category.get("id")
        if not category_id:
            errors.append("Category without id")
        if "items" not in category:
            errors.append(f"Category '{category_id}' missing items[]")
            continue
        if not isinstance(category["items"], list):
            errors.append(f"Category '{category_id}'.items must be a list")
            continue
        for idx, item in enumerate(category["items"]):
            location = f"{category_id}.items[{idx}]"
            if not isinstance(item, dict):
                errors.append(f"{location} must be an object")
                continue
            missing = sorted(required_item_fields - set(item))
            if missing:
                errors.append(f"{location} missing fields: {', '.join(missing)}")
            item_id = item.get("id")
            if item_id:
                if item_id in seen_ids:
                    errors.append(f"Duplicate item id: {item_id}")
                seen_ids.add(item_id)
            if item.get("priority") not in VALID_PRIORITIES:
                errors.append(f"{location} has invalid priority: {item.get('priority')!r}")
            if "done" in item and not isinstance(item.get("done"), bool):
                errors.append(f"{location}.done must be boolean")
            if item.get("review_needed") and item.get("confidence") == "alta":
                warnings.append(f"{item_id}: review_needed=true with confidence=alta")
            if item.get("source") == "manual" and item.get("auto_added_at"):
                warnings.append(f"{item_id}: manual item has auto_added_at")

    if not seen_ids:
        warnings.append("No items found in current sprint")

    agenda = sprint.get("agenda_tomorrow")
    if agenda is not None:
        if not isinstance(agenda, dict):
            errors.append("agenda_tomorrow must be an object")
        elif "events" in agenda and not isinstance(agenda.get("events"), list):
            errors.append("agenda_tomorrow.events must be a list")

    return errors, warnings


def build_system_state() -> Dict[str, Any]:
    ekyte_config = load_ekyte_config(write_defaults=True)
    return {
        "generated_at": now_br(),
        "refresh_errors": read_json(ERRORS_PATH, []),
        "refresh_trigger": read_json(TRIGGER_PATH, None),
        "ekyte_pending": read_ekyte_pending_normalized(),
        "ekyte_errors": read_json(EKYTE_ERRORS_PATH, []),
        "ekyte_config": ekyte_config,
        "last_sync": read_json(LAST_SYNC_PATH, None),
        "last_alerts": read_json(LAST_ALERTS_PATH, None),
    }


def default_due_date() -> str:
    if ZoneInfo:
        base = datetime.now(ZoneInfo("America/Sao_Paulo"))
    else:
        base = datetime.now()
    return (base + timedelta(days=2)).date().isoformat()


def normalize_key(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def as_id(value: Any) -> str:
    return str(value or "").strip()


def select_by_id(rows: List[Dict[str, Any]], row_id: Any) -> Optional[Dict[str, Any]]:
    wanted = as_id(row_id)
    if not wanted:
        return None
    return next((row for row in rows if as_id(row.get("id")) == wanted), None)


def ensure_tag_rows(rows: Any, names: List[str]) -> List[Dict[str, Any]]:
    existing = rows if isinstance(rows, list) else []
    by_name = {normalize_key(row.get("name")): row for row in existing if isinstance(row, dict)}
    result: List[Dict[str, Any]] = []
    for name in names:
        row = by_name.get(normalize_key(name), {})
        result.append({"name": name, "id": row.get("id")})
    for row in existing:
        if isinstance(row, dict) and normalize_key(row.get("name")) not in {normalize_key(name) for name in names}:
            result.append(row)
    return result


def load_ekyte_config(write_defaults: bool = False) -> Dict[str, Any]:
    config = read_json(EKYTE_CONFIG_PATH, {})
    if not isinstance(config, dict):
        config = {}
    changed = False
    defaults = {
        "default_workspace_id": "112225",
        "default_assignee_email": user_default_email(),
        "default_task_type_id": "68301",
        "workspaces": [],
        "task_types": [{"id": "68301", "name": "Tipo Ekyte 68301"}],
        "assignees": [],
    }
    for key, value in defaults.items():
        if key not in config:
            config[key] = value
            changed = True
    routine_tags = ensure_tag_rows(config.get("routine_tags"), ROUTINE_TAG_NAMES)
    week_tags = ensure_tag_rows(config.get("week_tags"), WEEK_TAG_NAMES)
    if config.get("routine_tags") != routine_tags:
        config["routine_tags"] = routine_tags
        changed = True
    if config.get("week_tags") != week_tags:
        config["week_tags"] = week_tags
        changed = True
    if write_defaults and changed:
        config["updated_at"] = now_br()
        write_json_atomic(EKYTE_CONFIG_PATH, config)
    return config


def item_is_ekyte_eligible(item: Dict[str, Any]) -> bool:
    if item.get("ekaite_task_id"):
        return False
    if item.get("review_needed"):
        return False
    return item.get("priority") == "urgente" and item.get("confidence") == "alta"


def parse_date_candidate(value: Any) -> Optional[str]:
    text = str(value or "")
    iso_match = re.search(r"\b(20\d{2})[-_/](\d{2})[-_/](\d{2})\b", text)
    if iso_match:
        candidate = "-".join(iso_match.groups())
        try:
            validate_date(candidate, "date")
            return candidate
        except ValueError:
            pass
    br_match = re.search(r"\b(\d{2})/(\d{2})/(20\d{2})\b", text)
    if br_match:
        day, month, year = br_match.groups()
        candidate = f"{year}-{month}-{day}"
        try:
            validate_date(candidate, "date")
            return candidate
        except ValueError:
            pass
    try:
        candidate = datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
        validate_date(candidate, "date")
        return candidate
    except Exception:  # noqa: BLE001
        return None


def meeting_date_for(item: Dict[str, Any], entry: Optional[Dict[str, Any]] = None) -> str:
    entry = entry or {}
    for value in [
        entry.get("meeting_date"),
        item.get("meeting_date"),
        item.get("source"),
        item.get("source_file"),
        item.get("auto_added_at"),
        entry.get("queued_at"),
        entry.get("created_at"),
    ]:
        parsed = parse_date_candidate(value)
        if parsed:
            return parsed
    return local_today()


def week_tag_name_for(date_value: str) -> str:
    validate_date(date_value, "meeting_date")
    week = datetime.strptime(date_value, "%Y-%m-%d").date().isocalendar().week
    week = max(1, min(52, int(week)))
    return f"SEMANA {week:02d}"


def infer_routine_tag(*parts: Any) -> Optional[str]:
    text = normalize_key(" ".join(str(part or "") for part in parts))
    if not text:
        return None
    patterns = [
        ("SPRINT GROWTH", ["sprint growth"]),
        ("QUALITY CONTROL", ["quality control", "quality check", "controle qualidade", "qc"]),
        ("ALINHAMENTO COMITÊ", ["alinhamento comite", "comite ops", "comite", "alinhamento"]),
        ("WAR", [" war ", "sala war", "war room"]),
        ("WEEKLY EXPANSÃO", ["weekly expansao", "weekly expansion", "expansao"]),
        ("AÇÃO GERENCIAL", ["acao gerencial", "gerencial", "daily coordenacao", "daily gerencia"]),
    ]
    padded = f" {text} "
    for tag_name, needles in patterns:
        if any(needle in padded for needle in needles):
            return tag_name
    return None


def tag_id_for(config: Dict[str, Any], key: str, name: Any) -> Optional[str]:
    wanted = normalize_key(name)
    if not wanted:
        return None
    for row in config.get(key, []) or []:
        if isinstance(row, dict) and normalize_key(row.get("name")) == wanted and row.get("id"):
            return as_id(row.get("id"))
    return None


def workspace_projects(config: Dict[str, Any], workspace_id: Any) -> List[Dict[str, Any]]:
    workspace = select_by_id(config.get("workspaces", []) or [], workspace_id)
    projects = workspace.get("projects", []) if workspace else []
    return projects if isinstance(projects, list) else []


def task_types_for(config: Dict[str, Any], workspace_id: Any) -> List[Dict[str, Any]]:
    workspace = select_by_id(config.get("workspaces", []) or [], workspace_id)
    workspace_types = workspace.get("task_types", []) if workspace else []
    if isinstance(workspace_types, list) and workspace_types:
        return workspace_types
    return config.get("task_types", []) or []


def resolve_first_id(rows: List[Dict[str, Any]]) -> Optional[str]:
    return as_id(rows[0].get("id")) if rows and isinstance(rows[0], dict) else None


def default_project_id(config: Dict[str, Any], workspace_id: Any) -> Optional[str]:
    projects = workspace_projects(config, workspace_id)
    q_project = next(
        (row for row in projects if re.search(r"\bq[1-4]\b|trimestr", normalize_key(row.get("name")))),
        None,
    )
    return as_id((q_project or projects[0]).get("id")) if projects else None


def resolve_row_name(rows: List[Dict[str, Any]], row_id: Any) -> Optional[str]:
    row = select_by_id(rows, row_id)
    return str(row.get("name")) if row and row.get("name") else None


def assignee_name_for(config: Dict[str, Any], email: Any) -> Optional[str]:
    wanted = str(email or "").strip().lower()
    if not wanted:
        return None
    for row in config.get("assignees", []) or []:
        if isinstance(row, dict) and str(row.get("email") or "").strip().lower() == wanted:
            return str(row.get("name") or "") or wanted
    return wanted


def build_ekyte_queue_entry(
    data: Dict[str, Any],
    category_id: str,
    category: Dict[str, Any],
    item: Dict[str, Any],
    due_date: str,
    selection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    selection = selection or {}
    meta = data.get("meta", {})
    evidence = item.get("alert_evidence") or {}
    config = load_ekyte_config(write_defaults=True)
    workspace_id = (
        selection.get("workspace_id")
        or item.get("workspace_id")
        or item.get("ekyte_workspace_id")
        or config.get("default_workspace_id")
    )
    workspace_label = (
        selection.get("workspace_label")
        or resolve_row_name(config.get("workspaces", []) or [], workspace_id)
        or item.get("workspace_label")
        or item.get("ekyte_workspace_label")
        or user_workspace_label()
    )
    project_id = selection.get("project_id") or item.get("project_id") or item.get("ekyte_project_id") or default_project_id(config, workspace_id)
    task_type_id = (
        selection.get("task_type_id")
        or item.get("task_type_id")
        or item.get("ekyte_task_type_id")
        or config.get("default_task_type_id")
        or ("68301" if select_by_id(task_types_for(config, workspace_id), "68301") else resolve_first_id(task_types_for(config, workspace_id)))
    )
    assignee_email = (
        selection.get("assignee_email")
        or item.get("assignee_email")
        or config.get("default_assignee_email")
        or user_default_email()
    )
    meeting_date = selection.get("meeting_date") or meeting_date_for(item, selection)
    week_tag_name = selection.get("week_tag_name") or week_tag_name_for(meeting_date)
    routine_tag_name = selection.get("routine_tag_name") or infer_routine_tag(item.get("source"), item.get("title"), category.get("name"))
    description_parts = [
        item.get("context") or "",
        f"Origem: {item.get('source') or '-'}",
    ]
    if item.get("source_quote"):
        description_parts.append(f"Trecho: {item.get('source_quote')}")
    if evidence.get("source_url"):
        description_parts.append(f"Evidência: {evidence.get('source_url')}")

    return {
        "item_id": item.get("id"),
        "sprint": meta.get("currentSprint"),
        "category_id": category_id,
        "category_name": category.get("name") or category_id,
        "workspace_id": as_id(workspace_id),
        "workspace_label": workspace_label,
        "project_id": as_id(project_id),
        "project_name": selection.get("project_name") or resolve_row_name(workspace_projects(config, workspace_id), project_id),
        "task_type_id": as_id(task_type_id),
        "task_type_name": selection.get("task_type_name") or resolve_row_name(task_types_for(config, workspace_id), task_type_id),
        "assignee_email": assignee_email,
        "assignee_name": selection.get("assignee_name") or assignee_name_for(config, assignee_email),
        "routine_tag_name": routine_tag_name,
        "routine_tag_id": selection.get("routine_tag_id") or tag_id_for(config, "routine_tags", routine_tag_name),
        "week_tag_name": week_tag_name,
        "week_tag_id": selection.get("week_tag_id") or tag_id_for(config, "week_tags", week_tag_name),
        "meeting_date": meeting_date,
        "title": item.get("title"),
        "description": "\n\n".join(part for part in description_parts if part),
        "due_date": due_date,
        "priority": item.get("priority"),
        "source": item.get("source"),
        "queued_at": selection.get("queued_at") or now_br(),
    }


def normalize_ekyte_entry(entry: Dict[str, Any], data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = data or read_json(DATA_PATH)
    item_id = str(entry.get("item_id") or "").strip()
    if not item_id:
        raise ValueError("item_id is required")
    try:
        category_id, category, item = find_current_item(data, item_id)
    except ValueError:
        category_id = str(entry.get("category_id") or "")
        category = {"id": category_id, "name": entry.get("category_name") or category_id}
        item = {
            "id": item_id,
            "title": entry.get("title"),
            "context": entry.get("description"),
            "source": entry.get("source"),
            "priority": entry.get("priority") or "urgente",
            "confidence": "alta",
        }
    due = str(entry.get("due_date") or entry.get("current_due_date") or default_due_date()).strip()
    validate_date(due, "due_date")
    merged = dict(entry)
    return build_ekyte_queue_entry(data, category_id, category, item, due, merged)


def read_ekyte_pending_normalized() -> List[Dict[str, Any]]:
    raw_queue = read_json_list(EKYTE_PENDING_PATH)
    if not raw_queue:
        return []
    try:
        data = read_json(DATA_PATH)
    except Exception:  # noqa: BLE001
        data = None
    normalized: List[Dict[str, Any]] = []
    for raw in raw_queue:
        if not isinstance(raw, dict):
            continue
        try:
            normalized.append(normalize_ekyte_entry(raw, data))
        except Exception as exc:  # noqa: BLE001
            fallback = dict(raw)
            fallback["_normalization_error"] = str(exc)
            normalized.append(fallback)
    return normalized


def queue_ekyte_item(item_id: str, due_date: str = "", selection: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = read_json(DATA_PATH)
    category_id, category, item = find_current_item(data, item_id)
    if not item_is_ekyte_eligible(item):
        raise ValueError("Item is not eligible for manual Ekyte queue")

    due = due_date or default_due_date()
    validate_date(due, "due_date")
    queue = read_json(EKYTE_PENDING_PATH, [])
    if not isinstance(queue, list):
        queue = []

    entry = build_ekyte_queue_entry(data, category_id, category, item, due, selection)
    queue = [queued for queued in queue if queued.get("item_id") != item_id]
    queue.append(entry)
    write_json_atomic(EKYTE_PENDING_PATH, queue)
    return entry


def mcp_arg(args: List[str], name: str) -> Optional[str]:
    try:
        idx = args.index(name)
        return args[idx + 1]
    except (ValueError, IndexError):
        return None


def load_ekyte_mcp_config() -> Tuple[str, Dict[str, str]]:
    cfg = read_json(MCP_CONFIG_PATH, {})
    servers = cfg.get("mcpServers", {}) if isinstance(cfg, dict) else {}
    server = servers.get("ekyte") or next(
        (payload for name, payload in servers.items() if "ekyte" in str(name).lower()),
        None,
    )
    if not isinstance(server, dict):
        raise ValueError("MCP Ekyte não encontrado em mcp.json")
    args = server.get("args", []) or []
    url = server.get("url") or mcp_arg(args, "--streamableHttp")
    if not url:
        raise ValueError("MCP Ekyte sem URL streamableHttp")
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    for idx, arg in enumerate(args):
        if arg == "--header" and idx + 1 < len(args) and ":" in args[idx + 1]:
            key, value = args[idx + 1].split(":", 1)
            headers[key.strip()] = value.strip()
    return str(url), headers


def parse_mcp_payload(raw: str) -> Dict[str, Any]:
    raw = raw.strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {"value": payload}
    except json.JSONDecodeError:
        pass
    for line in raw.splitlines():
        if line.startswith("data:"):
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                payload = json.loads(data)
                return payload if isinstance(payload, dict) else {"value": payload}
            except json.JSONDecodeError:
                continue
    raise ValueError("Resposta MCP inválida")


class EkyteMcpClient:
    def __init__(self) -> None:
        self.url, self.headers = load_ekyte_mcp_config()
        self.session_id: Optional[str] = None
        self.request_id = 0

    def request(self, method: str, params: Optional[Dict[str, Any]] = None, expect_response: bool = True) -> Dict[str, Any]:
        self.request_id += 1
        body: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if expect_response:
            body["id"] = self.request_id
        if params is not None:
            body["params"] = params
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                session = response.headers.get("mcp-session-id")
                if session:
                    self.session_id = session
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"MCP Ekyte HTTP {exc.code}: {raw[:500]}") from exc
        if not expect_response:
            return {}
        payload = parse_mcp_payload(raw)
        if payload.get("error"):
            raise ValueError(json.dumps(payload["error"], ensure_ascii=False))
        return payload

    def ensure_initialized(self) -> None:
        if self.session_id:
            return
        self.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "todos-dashboard-ekyte", "version": "1.0.0"},
            },
        )
        try:
            self.request("notifications/initialized", {}, expect_response=False)
        except Exception:  # noqa: BLE001
            pass

    def tools(self) -> List[Dict[str, Any]]:
        self.ensure_initialized()
        payload = self.request("tools/list", {})
        tools = payload.get("result", {}).get("tools", [])
        return tools if isinstance(tools, list) else []

    def create_task_tag_field(self) -> Tuple[str, bool]:
        """Returns (field_name, is_explicitly_supported).
        is_explicitly_supported=False means field was inferred from additionalProperties
        and the Ekyte API may silently ignore it — caller must mark task for manual tag."""
        for tool in self.tools():
            if tool.get("name") != "ekyte_create_task":
                continue
            schema = tool.get("inputSchema", {}) if isinstance(tool.get("inputSchema"), dict) else {}
            props = schema.get("properties", {})
            for field in ["tag_ids_csv", "tags_csv", "tag_names_csv"]:
                if field in props:
                    return field, True
            if schema.get("additionalProperties") is True:
                # Best-effort: send the field but API may ignore it
                return "tag_names_csv", False
        return "", False

    def create_task(self, entry: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """Returns (mcp_result, tags_confirmed).
        tags_confirmed=False means tags were sent best-effort but Ekyte may have ignored them."""
        tag_field, is_explicit = self.create_task_tag_field()
        if not tag_field:
            raise ValueError("MCP Ekyte não expôs campo de tags; não vou criar task sem tag")
        tags_value = ""
        if tag_field == "tag_ids_csv":
            if not entry.get("routine_tag_id") or not entry.get("week_tag_id"):
                raise ValueError("Tag de rotina e tag de semana precisam ter IDs para criar no Ekyte")
            tags_value = f"{entry['routine_tag_id']},{entry['week_tag_id']}"
        else:
            tags_value = f"{entry['routine_tag_name']},{entry['week_tag_name']}"
        arguments = {
            "artifact_ids_csv": "",
            "confirmation_text": "CREATE",
            "workspace_id": as_id(entry.get("workspace_id")),
            "ctc_task_type_id": as_id(entry.get("task_type_id")),
            "user_email": entry.get("assignee_email") or user_default_email(),
            "title": str(entry.get("title") or "").strip(),
            "description": str(entry.get("description") or "").strip(),
            "current_due_date": entry.get("due_date"),
            "priority_group": "90" if entry.get("priority") == "urgente" else "50",
            "quantity": "1",
            "estimated_time": str(entry.get("estimated_time") or "60"),
            "plan_task": "1",
            "ctc_task_project_id": as_id(entry.get("project_id")),
            "phase_start_date": entry.get("phase_start_date") or entry.get("meeting_date") or local_today(),
            "initial_executor_email": entry.get("assignee_email") or user_default_email(),
            tag_field: tags_value,
        }
        self.ensure_initialized()
        result = self.request("tools/call", {"name": "ekyte_create_task", "arguments": arguments})
        tool_result = result.get("result") if isinstance(result.get("result"), dict) else {}
        if tool_result.get("isError"):
            content = tool_result.get("content") or tool_result
            raise ValueError(json.dumps(content, ensure_ascii=False))
        return result, is_explicit


def coerce_ekyte_task_id(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d+", text):
        return None
    # Ekyte task ids in this workspace are long numeric ids. This avoids
    # confusing JSON-RPC request ids like {"id": 4} with created task ids.
    return text if int(text) >= 1000 else None


def recursive_find_task_id(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        if "jsonrpc" in payload and "result" in payload:
            return recursive_find_task_id(payload.get("result"))
        for key in ["task_id", "ctc_task_id", "taskId"]:
            task_id = coerce_ekyte_task_id(payload.get(key))
            if task_id:
                return task_id
        if "task" in normalize_key(" ".join(str(key) for key in payload.keys())):
            task_id = coerce_ekyte_task_id(payload.get("id"))
            if task_id:
                return task_id
        for value in payload.values():
            found = recursive_find_task_id(value)
            if found:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = recursive_find_task_id(value)
            if found:
                return found
    if isinstance(payload, str):
        try:
            return recursive_find_task_id(json.loads(payload))
        except json.JSONDecodeError:
            for pattern in [
                r"/tasks/(\d{4,})",
                r"\b(?:task[_ ]?id|task|tarefa|ekyte)\D{0,16}#?\s*(\d{4,})\b",
            ]:
                match = re.search(pattern, payload, re.I)
                if match:
                    task_id = coerce_ekyte_task_id(match.group(1))
                    if task_id:
                        return task_id
    return None


def mark_ekyte_task_created(
    item_id: str,
    task_id: str,
    entry: Dict[str, Any],
    raw_response: Dict[str, Any],
    tags_confirmed: bool = False,
) -> None:
    task_id = coerce_ekyte_task_id(task_id) or ""
    if not task_id:
        raise ValueError("ID Ekyte inválido; não vou marcar o todo como criado")
    data = read_json(DATA_PATH)
    _category_id, _category, item = find_current_item(data, item_id)
    url = f"https://app.ekyte.com/#/tasks/list/{task_id}/edit"
    item["ekaite_task_id"] = task_id
    item["ekyte_task_id"] = task_id
    item["ekaite_task_url"] = url
    item["ekyte_task_url"] = url
    item["ekaite_pending"] = False
    item["ekyte_created_at"] = now_br()
    item["ekyte_payload"] = {
        "workspace_id": entry.get("workspace_id"),
        "project_id": entry.get("project_id"),
        "task_type_id": entry.get("task_type_id"),
        "assignee_email": entry.get("assignee_email"),
        "routine_tag_name": entry.get("routine_tag_name"),
        "week_tag_name": entry.get("week_tag_name"),
    }
    item["ekyte_response_preview"] = json.dumps(raw_response, ensure_ascii=False)[:1200]
    if tags_confirmed:
        item["ekaite_status"] = "created"
        item["ekyte_status"] = "created"
        item.pop("ekyte_needs_manual_tag", None)
    else:
        item["ekaite_status"] = "created_without_tags"
        item["ekyte_status"] = "created_without_tags"
        item["ekyte_needs_manual_tag"] = True
        item["ekyte_tag_hint"] = (
            f"{entry.get('routine_tag_name', 'AÇÃO GERENCIAL')} + {entry.get('week_tag_name', 'SEMANA ?')}"
        )
    data["meta"]["lastUpdated"] = local_today()
    write_json_atomic(DATA_PATH, data)


def validate_ekyte_entry(entry: Dict[str, Any], tag_field: str = "") -> List[str]:
    errors: List[str] = []
    required = {
        "item_id": "item",
        "title": "título",
        "workspace_id": "workspace",
        "project_id": "projeto",
        "task_type_id": "tipo de task",
        "assignee_email": "responsável",
        "due_date": "prazo",
        "routine_tag_name": "tag de rotina",
        "week_tag_name": "tag de semana",
    }
    for key, label in required.items():
        if not entry.get(key):
            errors.append(f"Campo obrigatório ausente: {label}")
    for key in ["due_date", "meeting_date"]:
        if entry.get(key):
            try:
                validate_date(str(entry[key]), key)
            except ValueError as exc:
                errors.append(str(exc))
    if tag_field == "tag_ids_csv" and (not entry.get("routine_tag_id") or not entry.get("week_tag_id")):
        errors.append("O MCP exige IDs de tag, mas rotina/semana não têm IDs no config")
    return errors


def validate_ekyte_queue(item_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    data = read_json(DATA_PATH)
    raw_queue = read_json_list(EKYTE_PENDING_PATH)
    selected_ids = set(item_ids or [])
    entries = []
    for raw in raw_queue:
        if not isinstance(raw, dict):
            continue
        if selected_ids and raw.get("item_id") not in selected_ids:
            continue
        normalized = normalize_ekyte_entry(raw, data)
        entries.append(normalized)
    tag_field = ""
    tags_confirmed = False
    schema_error = ""
    try:
        tag_field, tags_confirmed = EkyteMcpClient().create_task_tag_field()
    except Exception as exc:  # noqa: BLE001
        schema_error = f"Não consegui consultar schema do MCP Ekyte: {exc}"
    results = []
    for entry in entries:
        errors = validate_ekyte_entry(entry, tag_field)
        if schema_error:
            errors.append(schema_error)
        elif not tag_field:
            errors.append("MCP Ekyte não expôs campo de tags; não vou criar task sem tag")
        elif not tags_confirmed:
            # Field inferred from additionalProperties — will be sent but may be ignored
            entry["_tag_warning"] = (
                "Tags serão enviadas via additionalProperties (best-effort). "
                "Task será criada com ekyte_needs_manual_tag=true até confirmação."
            )
        results.append({"entry": entry, "ok": not errors, "errors": errors})
    return {
        "ok": all(row["ok"] for row in results),
        "tag_field": tag_field,
        "tags_supported": bool(tag_field),
        "tags_confirmed": tags_confirmed,
        "count": len(results),
        "results": results,
    }


def create_manual_item(payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    data = read_json(DATA_PATH)
    errors, _warnings = validate_data(data)
    if errors:
        raise ValueError("Schema validation failed:\n- " + "\n- ".join(errors))

    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError("title is required")
    if len(title) > 180:
        raise ValueError("title must be at most 180 characters")

    category_id = str(payload.get("category_id", "projetos") or "projetos").strip()
    category = find_current_category(data, category_id)

    priority = str(payload.get("priority", "normal") or "normal").strip()
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"priority must be one of: {', '.join(sorted(VALID_PRIORITIES))}")

    confidence = str(payload.get("confidence", "alta") or "alta").strip().lower()
    if confidence == "media":
        confidence = "média"
    if confidence not in VALID_CONFIDENCES:
        raise ValueError("confidence must be alta, média or baixa")

    source = str(payload.get("source", "") or "").strip() or f"Manual — {local_today()}"
    item = {
        "id": unique_manual_item_id(data, title),
        "title": title,
        "context": str(payload.get("context", "") or "").strip(),
        "priority": priority,
        "done": False,
        "source": source,
        "confidence": confidence,
        "review_needed": bool(payload.get("review_needed", False)),
        "auto_added_at": now_br(),
    }

    source_quote = str(payload.get("source_quote", "") or "").strip()
    if source_quote:
        item["source_quote"] = source_quote

    category.setdefault("items", []).append(item)
    data["meta"]["lastUpdated"] = local_today()
    write_json_atomic(DATA_PATH, data)
    return category_id, item


def safe_json_for_script(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return raw.replace("</", "<\\/")


def render_dashboard(data: Dict[str, Any], system_state: Dict[str, Any]) -> str:
    user_cfg = load_user_config()
    owner = html.escape(str(
        data.get("meta", {}).get("owner")
        or user_cfg.get("user", {}).get("full_name")
        or "Jefferson Vieira"
    ))
    sprint_key = html.escape(str(data.get("meta", {}).get("currentSprint", "")))
    title = f"Todos — {owner}"

    return HTML_TEMPLATE.replace("__PAGE_TITLE__", title).replace(
        "__OWNER__", owner
    ).replace("__SPRINT_KEY__", sprint_key).replace(
        "__DATA_JSON__", safe_json_for_script(data)
    ).replace(
        "__SYSTEM_STATE_JSON__", safe_json_for_script(system_state)
    ).replace(
        "__USER_CONFIG_JSON__", safe_json_for_script(user_cfg)
    )


def generate_dashboard(
    data_path: Path = DATA_PATH,
    html_path: Path = HTML_PATH,
    quiet: bool = False,
    keep_transcripts: Optional[bool] = None,
) -> Tuple[int, int]:
    data = read_json(data_path)
    errors, warnings = validate_data(data)
    if errors:
        raise ValueError("Schema validation failed:\n- " + "\n- ".join(errors))

    html_payload = render_dashboard(data, build_system_state())
    write_text_atomic(html_path, html_payload)
    if keep_transcripts is None:
        keep_transcripts = KEEP_TRANSCRIPTS
    if not keep_transcripts:
        cleanup_transcripts(quiet=quiet)

    item_count = sum(1 for _ in iter_items(data))
    if not quiet:
        print(f"Generated {html_path} ({item_count} items, {len(warnings)} warnings)")
        for warning in warnings:
            print(f"Warning: {warning}", file=sys.stderr)
    return item_count, len(warnings)


def reset_current_sprint() -> Path:
    data = read_json(DATA_PATH)
    errors, _warnings = validate_data(data)
    if errors:
        raise ValueError("Schema validation failed:\n- " + "\n- ".join(errors))

    current_sprint = data["meta"]["currentSprint"]
    sprint = data["sprints"][current_sprint]
    archive_payload = {
        "archived_at": now_br(),
        "reason": "manual reset before rebuilding todos from meeting transcripts",
        "meta": data.get("meta", {}),
        "sprint_key": current_sprint,
        "sprint": sprint,
    }
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    archive_path = ARCHIVE_DIR / f"todos-reset-{current_sprint}-{stamp}.json"
    write_json_atomic(archive_path, archive_payload)

    for category in sprint.get("categories", []) or []:
        category["items"] = []
    data["meta"]["lastUpdated"] = datetime.now().date().isoformat()
    write_json_atomic(DATA_PATH, data)
    generate_dashboard(quiet=True)
    return archive_path


class TodosHandler(SimpleHTTPRequestHandler):
    server_version = "TodosDashboard/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        try:
            sys.stderr.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), fmt % args))
        except OSError:
            pass

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/status":
            self.send_json({"ok": True, "state": build_system_state()})
            return
        if parsed.path in {"/", ""}:
            self.path = "/todos-dashboard.html"
        super().do_GET()

    def do_HEAD(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/", ""}:
            self.path = "/todos-dashboard.html"
        super().do_HEAD()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/refresh":
            self.handle_refresh()
            return
        if parsed.path == "/api/ekyte-queue":
            self.handle_ekyte_queue()
            return
        if parsed.path == "/api/ekyte-create":
            self.handle_ekyte_create()
            return
        if parsed.path == "/api/ekyte-flush":
            self.handle_ekyte_flush()
            return
        if parsed.path == "/api/manual-task":
            self.handle_manual_task()
            return
        if parsed.path == "/write-json":
            self.handle_write_json()
            return
        if parsed.path == "/api/regenerate":
            self.handle_regenerate()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    def handle_refresh(self) -> None:
        try:
            payload = self.read_json_body()
            from_date = str(payload.get("from", "")).strip()
            to_date = str(payload.get("to", "")).strip()
            validate_date(from_date, "from")
            validate_date(to_date, "to")
            if from_date > to_date:
                raise ValueError("from must be before or equal to to")

            trigger = {
                "from": from_date,
                "to": to_date,
                "force_reprocess": bool(payload.get("force_reprocess", False)),
                "preset": str(payload.get("preset", "custom") or "custom"),
                "requested_at": now_br(),
            }
            write_json_atomic(TRIGGER_PATH, trigger)
            generate_dashboard(quiet=True)
            self.send_json({"ok": True, "trigger": trigger, "path": str(TRIGGER_PATH)})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def handle_regenerate(self) -> None:
        try:
            item_count, warning_count = generate_dashboard(quiet=True)
            self.send_json({"ok": True, "items": item_count, "warnings": warning_count})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def handle_ekyte_queue(self) -> None:
        try:
            payload = self.read_json_body()
            item_id = str(payload.get("item_id", "")).strip()
            if not item_id:
                raise ValueError("item_id is required")
            due_date = str(payload.get("due_date", "") or "").strip()
            selection = {key: payload.get(key) for key in [
                "workspace_id",
                "workspace_label",
                "project_id",
                "project_name",
                "task_type_id",
                "task_type_name",
                "assignee_email",
                "assignee_name",
                "routine_tag_name",
                "routine_tag_id",
                "week_tag_name",
                "week_tag_id",
                "meeting_date",
            ]}
            entry = queue_ekyte_item(item_id, due_date, selection)
            generate_dashboard(quiet=True)
            self.send_json({"ok": True, "queued": entry, "path": str(EKYTE_PENDING_PATH)})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def handle_ekyte_create(self) -> None:
        try:
            payload = self.read_json_body()
            item_id = str(payload.get("item_id", "")).strip()
            if not item_id:
                raise ValueError("item_id is required")
            due_date = str(payload.get("due_date", "") or "").strip() or default_due_date()
            data = read_json(DATA_PATH)
            category_id, category, item = find_current_item(data, item_id)
            if not item_is_ekyte_eligible(item):
                raise ValueError("Item is not eligible for Ekyte creation")
            entry = build_ekyte_queue_entry(data, category_id, category, item, due_date, payload)
            client = EkyteMcpClient()
            tag_field, tags_confirmed = client.create_task_tag_field()
            errors = validate_ekyte_entry(entry, tag_field)
            if not tag_field:
                errors.append("MCP Ekyte não expôs campo de tags; não vou criar task sem tag")
            if errors:
                raise ValueError("; ".join(errors))
            response, tags_confirmed = client.create_task(entry)
            task_id = recursive_find_task_id(response)
            if not task_id:
                raise ValueError("Task criada sem ID retornado pelo Ekyte; verifique manualmente antes de atualizar o dashboard")
            mark_ekyte_task_created(item_id, task_id, entry, response, tags_confirmed=tags_confirmed)
            queue = [row for row in read_json_list(EKYTE_PENDING_PATH) if row.get("item_id") != item_id]
            write_json_atomic(EKYTE_PENDING_PATH, queue)
            generate_dashboard(quiet=True)
            self.send_json({"ok": True, "task_id": task_id, "entry": entry, "response": response})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def handle_ekyte_flush(self) -> None:
        try:
            payload = self.read_json_body()
            item_ids = payload.get("item_ids")
            if item_ids is not None and not isinstance(item_ids, list):
                raise ValueError("item_ids must be a list")
            selected_ids = [str(item_id) for item_id in item_ids] if item_ids else None
            dry_run = bool(payload.get("dry_run", False))
            validation = validate_ekyte_queue(selected_ids)
            if dry_run:
                valid = bool(validation.pop("ok", False))
                self.send_json({"ok": True, "dry_run": True, "valid": valid, **validation})
                return
            if not validation.get("tags_supported"):
                raise ValueError("MCP Ekyte não expôs campo de tags; não vou criar task sem tag")
            # tags_confirmed=False means best-effort: tasks will be marked ekyte_needs_manual_tag=True

            client = EkyteMcpClient()
            successes: List[Dict[str, Any]] = []
            failures: List[Dict[str, Any]] = []
            remaining_queue = read_json_list(EKYTE_PENDING_PATH)
            for row in validation["results"]:
                entry = row["entry"]
                if not row["ok"]:
                    failures.append({"item_id": entry.get("item_id"), "errors": row["errors"], "entry": entry})
                    continue
                try:
                    response, tags_confirmed = client.create_task(entry)
                    task_id = recursive_find_task_id(response)
                    if not task_id:
                        raise ValueError("Task criada sem ID retornado pelo Ekyte")
                    mark_ekyte_task_created(str(entry["item_id"]), task_id, entry, response, tags_confirmed=tags_confirmed)
                    successes.append({"item_id": entry.get("item_id"), "task_id": task_id})
                    remaining_queue = [
                        queued for queued in remaining_queue
                        if queued.get("item_id") != entry.get("item_id")
                    ]
                except Exception as exc:  # noqa: BLE001
                    failures.append({"item_id": entry.get("item_id"), "error": str(exc), "entry": entry})

            write_json_atomic(EKYTE_PENDING_PATH, remaining_queue)
            if failures:
                current_errors = read_json_list(EKYTE_ERRORS_PATH)
                current_errors.extend({"at": now_br(), **failure} for failure in failures)
                write_json_atomic(EKYTE_ERRORS_PATH, current_errors[-200:])
            generate_dashboard(quiet=True)
            self.send_json(
                {
                    "ok": not failures,
                    "successes": successes,
                    "failures": failures,
                    "remaining": len(remaining_queue),
                },
                status=HTTPStatus.OK if not failures else HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def handle_manual_task(self) -> None:
        try:
            payload = self.read_json_body()
            category_id, item = create_manual_item(payload)
            item_count, warning_count = generate_dashboard(quiet=True)
            self.send_json(
                {
                    "ok": True,
                    "category_id": category_id,
                    "item": item,
                    "items": item_count,
                    "warnings": warning_count,
                    "path": str(DATA_PATH),
                }
            )
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def handle_write_json(self) -> None:
        try:
            payload = self.read_json_body()
            target = str(payload.get("path", "")).strip()
            if target not in {".todos/ekyte-pending.json", "ekyte-pending.json"}:
                raise ValueError("Only .todos/ekyte-pending.json can be written")
            data = payload.get("data")
            if not isinstance(data, list):
                raise ValueError("data must be a JSON array")
            write_json_atomic(EKYTE_PENDING_PATH, data)
            generate_dashboard(quiet=True)
            self.send_json({"ok": True, "path": str(EKYTE_PENDING_PATH), "count": len(data)})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def send_json(self, payload: Dict[str, Any], status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def translate_path(self, path: str) -> str:
        # Keep SimpleHTTPRequestHandler inside BASE_DIR.
        parsed = urllib.parse.urlparse(path)
        clean_path = posixpath.normpath(urllib.parse.unquote(parsed.path))
        parts = [part for part in clean_path.split("/") if part and part not in {os.curdir, os.pardir}]
        target = BASE_DIR
        for part in parts:
            target = target / part
        return str(target)


def serve(host: str, port: int, keep_transcripts: bool = False) -> None:
    global KEEP_TRANSCRIPTS  # noqa: PLW0603
    KEEP_TRANSCRIPTS = keep_transcripts
    generate_dashboard(quiet=True, keep_transcripts=keep_transcripts)
    httpd = ThreadingHTTPServer((host, port), TodosHandler)
    url = f"http://{host}:{port}/"
    print(f"Serving dashboard at {url}")
    print(f"POST /api/refresh writes {TRIGGER_PATH}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")


def watch(interval: float, keep_transcripts: bool = False) -> None:
    global KEEP_TRANSCRIPTS  # noqa: PLW0603
    KEEP_TRANSCRIPTS = keep_transcripts
    last_mtime = 0.0
    print(f"Watching {DATA_PATH}")
    while True:
        try:
            current_mtime = DATA_PATH.stat().st_mtime
            if current_mtime != last_mtime:
                generate_dashboard(keep_transcripts=keep_transcripts)
                last_mtime = current_mtime
        except Exception as exc:  # noqa: BLE001
            print(f"Generate failed: {exc}", file=sys.stderr)
        time.sleep(interval)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Jefferson's todos dashboard")
    parser.add_argument("--validate", action="store_true", help="Validate todos-data.json and exit")
    parser.add_argument("--watch", action="store_true", help="Regenerate when todos-data.json changes")
    parser.add_argument("--serve", action="store_true", help="Serve the dashboard with refresh endpoints")
    parser.add_argument("--reset-current-sprint", action="store_true", help="Archive and clear items from the current sprint")
    parser.add_argument("--host", default="127.0.0.1", help="Host for --serve")
    parser.add_argument("--port", type=int, default=8787, help="Port for --serve")
    parser.add_argument("--interval", type=float, default=1.0, help="Polling interval for --watch")
    parser.add_argument("--keep-transcripts", action="store_true", help="Do not remove downloaded transcripts after generating")
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    try:
        data = read_json(DATA_PATH)
        errors, warnings = validate_data(data)
        if errors:
            print("Schema validation failed:", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        if args.validate:
            print(f"OK: {DATA_PATH}")
            if warnings:
                print("Warnings:")
                for warning in warnings:
                    print(f"- {warning}")
            return 0
        if args.reset_current_sprint:
            archive_path = reset_current_sprint()
            print(f"Reset current sprint. Archive: {archive_path}")
            return 0
        if args.serve:
            serve(args.host, args.port, keep_transcripts=args.keep_transcripts)
            return 0
        if args.watch:
            watch(args.interval, keep_transcripts=args.keep_transcripts)
            return 0
        generate_dashboard(keep_transcripts=args.keep_transcripts)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__PAGE_TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #000000;
    --panel: #0d0d0d;
    --panel-strong: #141414;
    --panel-soft: #080808;
    --border: #1f1f1f;
    --border-soft: #181818;
    --text: #f2f2f2;
    --muted: #A1A1AA;
    --action: #E8001C;
    --action-hover: #ff0020;
    --action-dim: rgba(232,0,28,.14);
    --risk: #ff3b5c;
    --risk-dim: rgba(255,59,92,.13);
    --warn: #f5923a;
    --warn-dim: rgba(245,146,58,.13);
    --success: #27c96a;
    --success-dim: rgba(39,201,106,.12);
    --info: #3ecfca;
    --info-dim: rgba(62,207,202,.12);
    --highlight: #f5d020;
    --highlight-dim: rgba(245,208,32,.11);
    --shadow: 0 16px 48px rgba(0,0,0,.64);
    --radius: 6px;
    --font-title: 'Oswald', 'Arial Narrow', sans-serif;
    --font-body: 'Inter', "Segoe UI", system-ui, -apple-system, sans-serif;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { color-scheme: dark; }
  body {
    min-height: 100vh;
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-body);
    font-size: 14px; line-height: 1.5;
  }
  button, input, select, textarea { font: inherit; color: inherit; }
  button { cursor: pointer; border: none; background: none; }
  a { color: inherit; text-decoration: none; }
  /* Topbar */
  .topbar {
    position: sticky; top: 0; z-index: 50;
    display: grid; grid-template-columns: minmax(200px,1fr) minmax(240px,420px) auto;
    gap: 14px; align-items: center; padding: 10px 22px;
    border-bottom: 1px solid var(--border);
    background: rgba(15,17,23,.94); backdrop-filter: blur(20px);
  }
  .brand-title { font-family: var(--font-title); font-size: 16px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .brand-meta { margin-top: 1px; font-size: 11px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .search-wrap { position: relative; }
  .search-wrap input {
    width: 100%; height: 36px; padding: 0 36px 0 11px;
    border: 1px solid var(--border); border-radius: var(--radius);
    background: var(--panel); outline: none;
  }
  .search-wrap input:focus { border-color: var(--action); box-shadow: 0 0 0 3px var(--action-dim); }
  .search-icon { position: absolute; right: 11px; top: 8px; color: var(--muted); pointer-events: none; font-size: 16px; }
  .topbar-actions { display: flex; gap: 7px; align-items: center; justify-content: flex-end; }
  /* Buttons */
  .btn {
    display: inline-flex; align-items: center; gap: 5px;
    min-height: 34px; border: 1px solid var(--border); border-radius: var(--radius);
    padding: 0 11px; background: var(--panel);
    font-size: 13px; font-weight: 640; white-space: nowrap;
    transition: border-color .15s, background .15s;
  }
  .btn:hover { border-color: var(--action); }
  .btn.primary { background: var(--action); border-color: var(--action); color: #fff; }
  .btn.primary:hover { background: var(--action-hover); }
  .btn.danger { background: var(--risk-dim); border-color: rgba(240,68,96,.38); color: #ffcdd5; }
  .btn:disabled { opacity: .42; cursor: not-allowed; filter: grayscale(.35); }
  .btn:disabled:hover { border-color: var(--border); background: var(--panel); }
  .btn.primary:disabled { background: #471017; border-color: #5a1820; color: #b8a3a7; }
  /* Page */
  .page { max-width: 1100px; margin: 0 auto; padding: 18px 22px 36px; }
  /* Error banner */
  .status-banner {
    display: none; margin-bottom: 12px;
    border: 1px solid rgba(240,68,96,.35); border-radius: var(--radius);
    background: var(--risk-dim); padding: 11px 13px;
  }
  .status-banner.visible { display: flex; gap: 12px; align-items: center; justify-content: space-between; }
  .status-title { font-size: 13px; font-weight: 750; }
  .status-detail { margin-top: 2px; font-size: 11px; color: var(--muted); }
  /* Panels */
  .panel {
    display: none; margin-bottom: 12px;
    border: 1px solid var(--border); border-radius: var(--radius);
    background: var(--panel); box-shadow: var(--shadow); padding: 13px;
  }
  .panel.visible { display: block; }
  .refresh-grid { display: grid; grid-template-columns: 150px 1fr 1fr auto auto; gap: 9px; align-items: end; }
  .manual-grid { display: grid; grid-template-columns: 170px minmax(200px,1fr) 130px 130px auto; gap: 9px; align-items: end; }
  .field-full { grid-column: 1 / -1; }
  .field label { display: block; margin-bottom: 4px; font-size: 10px; color: var(--muted); font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }
  .field input, .field select, .field textarea {
    width: 100%; border: 1px solid var(--border); border-radius: var(--radius);
    background: var(--panel-soft); outline: none;
  }
  .field input:focus, .field select:focus, .field textarea:focus { border-color: var(--action); box-shadow: 0 0 0 2px var(--action-dim); }
  .field input, .field select { height: 34px; padding: 0 9px; }
  .field textarea { min-height: 64px; padding: 8px 9px; resize: vertical; }
  .check-field { display: flex; align-items: center; gap: 7px; min-height: 34px; color: var(--muted); font-size: 13px; white-space: nowrap; }
  .check-field input[type=checkbox] { width: 15px; height: 15px; accent-color: var(--action); }
  .panel-msg { margin-top: 9px; min-height: 16px; font-size: 11px; color: var(--muted); }
  .panel-msg.ok { color: var(--success); }
  .panel-msg.err { color: var(--warn); }
  /* Stat buttons */
  .stats { display: grid; grid-template-columns: repeat(6,minmax(0,1fr)); gap: 1px; margin-bottom: 16px; background: var(--border); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
  .stat-btn {
    display: flex; flex-direction: column; align-items: flex-start;
    min-height: 76px; padding: 14px 16px;
    background: var(--panel); cursor: pointer; text-align: left;
    transition: background .15s;
    position: relative;
  }
  .stat-btn::after { content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 2px; background: transparent; transition: background .15s; }
  .stat-btn:hover { background: var(--panel-strong); }
  .stat-btn:hover::after { background: var(--border); }
  .stat-btn.active { background: var(--panel-strong); }
  .stat-btn.active::after { background: var(--action); }
  .stat-value { font-family: var(--font-title); font-size: 32px; font-weight: 700; line-height: 1; color: var(--text); }
  .stat-btn.active .stat-value { color: var(--action); }
  .stat-btn[data-scope="alerts"] .stat-value { color: var(--action); }
  .stat-label { margin-top: 6px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); font-family: var(--font-body); }
  /* Filter bar (categories + progress) */
  .filter-bar {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 14px; padding: 8px 0;
    border-bottom: 1px solid var(--border);
  }
  .filter-bar .chips { margin-bottom: 0; flex: 1; flex-wrap: wrap; gap: 6px; }
  .progress-inline { display: flex; align-items: center; gap: 10px; flex-shrink: 0; white-space: nowrap; font-size: 11px; color: var(--muted); }
  .progress-track-sm { width: 80px; height: 4px; border-radius: 999px; background: var(--border); overflow: hidden; }
  .progress-fill-sm { height: 100%; background: var(--action); transition: width .3s ease; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .chip {
    display: inline-flex; align-items: center; gap: 5px;
    min-height: 28px; padding: 0 10px;
    border: 1px solid var(--border); border-radius: 999px;
    background: transparent; color: var(--muted);
    font-size: 11px; font-weight: 600; cursor: pointer;
    transition: border-color .12s, background .12s, color .12s;
    white-space: nowrap;
  }
  .chip:hover { border-color: var(--muted); color: var(--text); }
  .chip.active { color: #fff; border-color: var(--action); background: var(--action); }
  .chip .count { font-weight: 700; opacity: .75; }
  /* Category blocks */
  .category { border: 1px solid var(--border); border-radius: var(--radius); background: var(--panel); margin-bottom: 10px; overflow: hidden; }
  .category.alertas { border-color: rgba(240,68,96,.38); }
  .category-head {
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
    min-height: 44px; padding: 0 13px;
    background: var(--panel-strong); border-bottom: 1px solid var(--border);
  }
  .category.alertas .category-head { background: var(--risk-dim); }
  .category-main {
    flex: 1; min-width: 0; min-height: 44px;
    display: flex; align-items: center;
    background: none; border: none; text-align: left; cursor: pointer;
  }
  .category-name { font-family: var(--font-title); font-size: 14px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; }
  .category-meta { font-size: 11px; color: var(--muted); margin-top: 1px; }
  .category-actions { display: flex; align-items: center; gap: 7px; flex-shrink: 0; }
  .badge {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 26px; height: 22px; padding: 0 7px;
    border-radius: 999px; background: var(--action-dim);
    color: #fff; font-size: 11px; font-weight: 800;
  }
  .badge.risk { background: var(--risk); }
  .category-body.collapsed { display: none; }
  /* Task items */
  .item {
    display: grid; grid-template-columns: 32px minmax(0,1fr);
    gap: 8px; padding: 11px 13px;
    border-top: 1px solid var(--border-soft);
    transition: background .1s;
  }
  .item:first-child { border-top: none; }
  .item:hover { background: rgba(255,255,255,.02); }
  .item.done { opacity: .4; }
  .item.done .item-title { text-decoration: line-through; color: var(--muted); }
  .item.alert-item { box-shadow: inset 3px 0 0 var(--risk); }
  .item-check-col { display: flex; align-items: flex-start; padding-top: 2px; }
  .checkbox {
    width: 18px; height: 18px; flex-shrink: 0;
    border: 2px solid var(--border); border-radius: 4px;
    background: transparent; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    transition: border-color .12s, background .12s;
  }
  .checkbox:hover { border-color: var(--action); }
  .checkbox.checked { background: var(--success); border-color: var(--success); }
  .checkbox.checked::after { content: "✓"; color: #fff; font-size: 11px; font-weight: 900; line-height: 1; }
  .item-body { min-width: 0; }
  .item-row1 { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
  .item-title { font-size: 13px; font-weight: 680; line-height: 1.35; overflow-wrap: anywhere; }
  .item-context { margin-top: 3px; color: var(--muted); font-size: 11px; line-height: 1.45; overflow-wrap: anywhere; }
  .item-quote { margin-top: 6px; padding: 5px 8px; border-left: 2px solid var(--border); color: #b8c0d6; background: rgba(255,255,255,.02); font-size: 11px; line-height: 1.45; }
  .item-action { margin-top: 5px; color: #f5d9b0; font-size: 11px; line-height: 1.4; }
  .item-meta { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin-top: 7px; }
  .item-source { color: var(--muted); font-size: 10px; overflow-wrap: anywhere; }
  /* Tags */
  .tag {
    display: inline-flex; align-items: center;
    min-height: 18px; padding: 0 5px;
    border: 1px solid var(--border); border-radius: 4px;
    background: var(--panel-soft); color: var(--muted);
    font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .02em;
    white-space: nowrap;
  }
  .tag.urgente { color: #ffcdd5; background: var(--risk-dim); border-color: rgba(240,68,96,.32); }
  .tag.normal { color: #d5d8ff; background: var(--action-dim); border-color: rgba(91,103,245,.30); }
  .tag.recorrente { color: #c4f5f3; background: var(--info-dim); border-color: rgba(62,207,202,.28); }
  .tag.alta { color: #c4ffe0; background: var(--success-dim); border-color: rgba(39,201,106,.28); }
  .tag.media, .tag.review { color: #fff3b0; background: var(--highlight-dim); border-color: rgba(245,208,32,.28); }
  .tag.alert { color: #ffcdd5; background: var(--risk-dim); border-color: rgba(240,68,96,.32); }
  .tag.follow { color: #c4e4ff; background: rgba(62,130,245,.13); border-color: rgba(62,130,245,.32); }
  .tag.ekyte-ok { color: #c4ffe0; background: var(--success-dim); border-color: rgba(39,201,106,.28); }
  .tag.ekyte-pending { color: #fff3b0; background: var(--highlight-dim); border-color: rgba(245,208,32,.28); }
  .tag.ekyte-notag { color: #ffe4c8; background: var(--warn-dim); border-color: rgba(245,146,58,.40); }
  a.tag { text-decoration: none; }
  a.tag:hover { filter: brightness(1.15); }
  /* Mini button */
  .mini-btn {
    display: inline-flex; align-items: center;
    min-height: 18px; padding: 0 6px;
    border: 1px solid rgba(62,207,202,.32); border-radius: 4px;
    background: var(--info-dim); color: #c4f5f3;
    font-size: 10px; font-weight: 850; text-transform: uppercase; cursor: pointer;
  }
  .mini-btn:hover { border-color: var(--info); }
  .hide-done-btn {
    min-height: 24px; padding: 0 8px;
    border: 1px solid var(--border); border-radius: 4px;
    background: var(--panel-soft); color: var(--muted);
    font-size: 10px; font-weight: 800; text-transform: uppercase; cursor: pointer;
  }
  .hide-done-btn:hover { border-color: var(--action); color: var(--text); }
  .hide-done-btn.active { border-color: rgba(39,201,106,.42); background: var(--success-dim); color: #c4ffe0; }
  /* Item history log */
  .history-log { margin-top: 7px; display: grid; gap: 5px; }
  .history-entry { border-left: 2px solid rgba(39,201,106,.38); background: rgba(39,201,106,.05); padding: 5px 8px; font-size: 10px; line-height: 1.4; color: #ccd4e8; }
  .history-entry.reopened { border-left-color: rgba(245,208,32,.42); background: rgba(245,208,32,.05); }
  .history-entry strong { color: #fff; font-weight: 800; }
  .history-note { margin-top: 2px; color: var(--muted); overflow-wrap: anywhere; }
  /* Empty state */
  .empty-state { padding: 18px 13px; color: var(--muted); font-size: 12px; text-align: center; }
  /* History / Follow views */
  .view-section { display: none; }
  .view-section.visible { display: block; }
  .month-group { margin-bottom: 20px; }
  .month-title { font-family: var(--font-title); font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); padding: 5px 0; border-bottom: 1px solid var(--border); margin-bottom: 9px; }
  .hist-card { border: 1px solid var(--border); border-radius: var(--radius); background: var(--panel); padding: 11px 13px; margin-bottom: 7px; }
  .hist-card-title { font-size: 13px; font-weight: 680; line-height: 1.35; overflow-wrap: anywhere; }
  .hist-card-meta { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; margin-top: 5px; font-size: 10px; color: var(--muted); }
  .hist-card-note { margin-top: 7px; padding: 5px 8px; border-left: 2px solid rgba(39,201,106,.38); background: rgba(39,201,106,.05); color: #ccd4e8; font-size: 11px; line-height: 1.4; overflow-wrap: anywhere; }
  .follow-card { border: 1px solid rgba(62,130,245,.26); border-radius: var(--radius); background: var(--panel); padding: 11px 13px; margin-bottom: 7px; }
  .follow-card-title { font-size: 13px; font-weight: 680; line-height: 1.35; overflow-wrap: anywhere; }
  .follow-card-meta { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; margin-top: 5px; font-size: 10px; color: var(--muted); }
  .follow-card-note { margin-top: 7px; padding: 5px 8px; border-left: 2px solid rgba(62,130,245,.38); background: rgba(62,130,245,.07); color: #c4e4ff; font-size: 11px; line-height: 1.4; overflow-wrap: anywhere; }
  .follow-card-actions { display: flex; gap: 6px; margin-top: 9px; flex-wrap: wrap; }
  .ekyte-other-field { margin-top: 5px; }
  .ekyte-other-field.hidden { display: none; }
  /* System strip */
  .system-strip { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 16px; padding: 9px 13px; border: 1px solid var(--border-soft); border-radius: var(--radius); background: var(--panel-soft); font-size: 11px; color: var(--muted); }
  .sys-item strong { color: var(--text); margin-left: 3px; }
  .sys-item.server-ok strong { color: var(--success); }
  .sys-item.server-off strong { color: var(--warn); }
  /* Modal */
  .modal-backdrop {
    position: fixed; inset: 0; z-index: 60;
    display: flex; align-items: center; justify-content: center; padding: 18px;
    background: rgba(5,7,14,.78); backdrop-filter: blur(12px);
  }
  .modal-backdrop.hidden { display: none; }
  .modal-card {
    width: min(520px,100%); max-height: calc(100vh - 40px); overflow-y: auto;
    border: 1px solid var(--border); border-radius: var(--radius);
    background: #121620; box-shadow: var(--shadow); padding: 18px;
  }
  .modal-card.wide { width: min(920px,100%); }
  .modal-title { font-family: var(--font-title); font-size: 18px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; line-height: 1.25; }
  .modal-task { margin-top: 7px; color: var(--muted); font-size: 12px; line-height: 1.45; overflow-wrap: anywhere; }
  .modal-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 9px; margin-top: 13px; }
  .modal-grid .field-full { grid-column: 1 / -1; }
  .modal-msg { min-height: 18px; margin-top: 9px; font-size: 11px; color: var(--muted); }
  .modal-msg.ok { color: var(--success); }
  .modal-msg.err { color: var(--warn); }
  .queue-tools { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 13px; padding-bottom: 8px; border-bottom: 1px solid var(--border-soft); }
  .queue-list { display: grid; gap: 7px; max-height: 42vh; overflow: auto; margin-top: 9px; padding-right: 3px; }
  .queue-row { display: grid; grid-template-columns: 22px minmax(0,1fr); gap: 8px; padding: 9px; border: 1px solid var(--border-soft); border-radius: var(--radius); background: var(--panel-soft); }
  .queue-row.ok { border-color: rgba(39,201,106,.30); }
  .queue-row.err { border-color: rgba(245,146,58,.36); }
  .queue-row input { margin-top: 2px; accent-color: var(--action); }
  .queue-title { font-size: 12px; font-weight: 750; line-height: 1.35; overflow-wrap: anywhere; }
  .queue-meta { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 5px; color: var(--muted); font-size: 10px; }
  .queue-errors { margin-top: 5px; color: var(--warn); font-size: 10px; line-height: 1.4; }
  .queue-edit-btn {
    min-height: 18px; padding: 0 6px; border: 1px solid var(--border);
    border-radius: 4px; background: transparent; color: var(--muted);
    font-size: 10px; font-weight: 850; text-transform: uppercase;
  }
  .queue-edit-btn:hover { color: var(--text); border-color: var(--action); }
  .modal-card textarea {
    width: 100%; min-height: 110px; margin-top: 13px; resize: vertical;
    border: 1px solid var(--border); border-radius: var(--radius);
    background: var(--panel-soft); padding: 8px 10px;
  }
  .modal-card textarea:focus { outline: none; border-color: var(--action); box-shadow: 0 0 0 2px var(--action-dim); }
  .modal-follow {
    display: flex; align-items: center; gap: 8px; margin-top: 11px;
    padding: 9px 11px; border: 1px solid var(--border-soft); border-radius: var(--radius);
    background: var(--panel-soft); font-size: 12px; color: var(--muted); cursor: pointer;
  }
  .modal-follow input { width: 15px; height: 15px; accent-color: var(--action); cursor: pointer; flex-shrink: 0; }
  .modal-follow label { cursor: pointer; user-select: none; }
  .modal-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 13px; }
  /* Toast */
  .toast {
    position: fixed; right: 16px; bottom: 16px; z-index: 100;
    display: none; max-width: 340px;
    border: 1px solid var(--border); border-radius: var(--radius);
    background: var(--panel); padding: 11px 13px; box-shadow: var(--shadow); font-size: 13px;
  }
  .toast.visible { display: block; }
  .toast.ok { border-color: rgba(39,201,106,.38); }
  .toast.err { border-color: rgba(245,146,58,.40); }
  .toast.warn { border-color: rgba(245,208,32,.38); }
  .toast.info { border-color: rgba(62,207,202,.38); }
  .hidden { display: none !important; }
  /* Responsive */
  @media (max-width: 900px) {
    .topbar { grid-template-columns: 1fr; gap: 9px; }
    .topbar-actions { justify-content: flex-start; flex-wrap: wrap; }
    .stats { grid-template-columns: repeat(3,minmax(0,1fr)); }
    .refresh-grid { grid-template-columns: 1fr 1fr; }
    .manual-grid { grid-template-columns: 1fr 1fr; }
  }
  @media (max-width: 560px) {
    .topbar, .page { padding-left: 12px; padding-right: 12px; }
    .stats { grid-template-columns: repeat(2,minmax(0,1fr)); }
    .refresh-grid, .manual-grid { grid-template-columns: 1fr; }
    .topbar-actions { overflow-x: auto; flex-wrap: nowrap; padding-bottom: 2px; }
    .topbar-actions .btn { flex-shrink: 0; }
    .category-head { flex-wrap: wrap; gap: 7px; padding: 8px 11px; }
    .modal-card { padding: 14px; }
    .modal-grid { grid-template-columns: 1fr; }
    .modal-grid .field-full { grid-column: auto; }
    .modal-actions { gap: 6px; }
    .modal-actions .btn { flex: 1; justify-content: center; }
  }
</style>
</head>
<body>
<header class="topbar">
  <div class="brand">
    <div class="brand-title">Todos — __OWNER__</div>
    <div class="brand-meta" id="headerMeta">Sprint __SPRINT_KEY__</div>
  </div>
  <div class="search-wrap">
    <input id="searchInput" type="search" placeholder="Buscar título, contexto, fonte ou anotação…" autocomplete="off" aria-label="Buscar tasks">
    <span class="search-icon" aria-hidden="true">⌕</span>
  </div>
  <div class="topbar-actions">
    <button class="btn hidden" id="flushEkyteBtn" type="button">Fila Ekyte (0)</button>
    <button class="btn hidden" id="clearFiltersBtn" type="button">✕ Limpar filtro</button>
    <button class="btn" id="manualToggleBtn" type="button">+ Task</button>
    <button class="btn primary" id="refreshToggleBtn" type="button">Atualizar</button>
  </div>
</header>

<main class="page">
  <section class="status-banner" id="errorBanner" role="alert"></section>

  <section class="panel" id="refreshPanel">
    <div class="refresh-grid">
      <div class="field">
        <label for="refreshPreset">Preset</label>
        <select id="refreshPreset">
          <option value="yesterday">Ontem</option>
          <option value="today">Hoje</option>
          <option value="last7">Últimos 7 dias</option>
          <option value="custom">Manual</option>
        </select>
      </div>
      <div class="field">
        <label for="refreshFrom">De</label>
        <input id="refreshFrom" type="date">
      </div>
      <div class="field">
        <label for="refreshTo">Até</label>
        <input id="refreshTo" type="date">
      </div>
      <label class="check-field"><input id="refreshForce" type="checkbox"> Forçar</label>
      <button class="btn primary" id="createTriggerBtn" type="button">Criar trigger</button>
    </div>
    <div class="panel-msg" id="refreshMessage" aria-live="polite"></div>
  </section>

  <section class="panel" id="manualPanel">
    <div class="manual-grid">
      <div class="field">
        <label for="manualCategory">Categoria</label>
        <select id="manualCategory"></select>
      </div>
      <div class="field">
        <label for="manualTitle">Título</label>
        <input id="manualTitle" type="text" maxlength="180" placeholder="Ação objetiva">
      </div>
      <div class="field">
        <label for="manualPriority">Prioridade</label>
        <select id="manualPriority">
          <option value="normal">Normal</option>
          <option value="urgente">Urgente</option>
          <option value="recorrente">Recorrente</option>
        </select>
      </div>
      <div class="field">
        <label for="manualConfidence">Confiança</label>
        <select id="manualConfidence">
          <option value="alta">Alta</option>
          <option value="média">Média</option>
        </select>
      </div>
      <button class="btn primary" id="createManualBtn" type="button">Adicionar</button>
      <div class="field field-full">
        <label for="manualContext">Contexto</label>
        <textarea id="manualContext" placeholder="Contexto curto, combinado ou motivo"></textarea>
      </div>
      <div class="field">
        <label for="manualSource">Fonte</label>
        <input id="manualSource" type="text" placeholder="Manual">
      </div>
      <label class="check-field"><input id="manualReview" type="checkbox"> Revisar</label>
    </div>
    <div class="panel-msg" id="manualMessage" aria-live="polite"></div>
  </section>

  <div class="stats" id="stats"></div>
  <div class="filter-bar" id="filterBar"></div>
  <div id="categories"></div>
  <div class="view-section" id="historyView"></div>
  <div class="view-section" id="followView"></div>
  <div class="system-strip" id="systemStrip"></div>
</main>

<div class="modal-backdrop hidden" id="completionModal" role="dialog" aria-modal="true" aria-labelledby="completionModalTitle">
  <div class="modal-card">
    <div class="modal-title" id="completionModalTitle">Concluir task</div>
    <div class="modal-task" id="completionTaskTitle"></div>
    <textarea id="completionNote" placeholder="Contexto rápido, decisão tomada, link ou próximo passo. Opcional."></textarea>
    <div class="modal-follow">
      <input type="checkbox" id="completionFollow">
      <label for="completionFollow">Follow — manter no radar após concluir</label>
    </div>
    <div class="modal-actions">
      <button class="btn" id="completionCancelBtn" type="button">Cancelar</button>
      <button class="btn" id="completionSkipBtn" type="button">Concluir sem nota</button>
      <button class="btn primary" id="completionSaveBtn" type="button">Concluir</button>
    </div>
  </div>
</div>

<div class="modal-backdrop hidden" id="followDismissModal" role="dialog" aria-modal="true" aria-labelledby="followDismissTitle">
  <div class="modal-card">
    <div class="modal-title" id="followDismissTitle">Concluir follow</div>
    <div class="modal-task" id="followDismissTaskTitle"></div>
    <textarea id="followDismissNote" placeholder="Nota final opcional antes de remover do radar."></textarea>
    <div class="modal-actions">
      <button class="btn" id="followDismissCancelBtn" type="button">Cancelar</button>
      <button class="btn" id="followDismissSkipBtn" type="button">Remover sem nota</button>
      <button class="btn primary" id="followDismissSaveBtn" type="button">Concluir follow</button>
    </div>
  </div>
</div>

<div class="modal-backdrop hidden" id="ekyteModal" role="dialog" aria-modal="true" aria-labelledby="ekyteModalTitle">
  <div class="modal-card wide">
    <div class="modal-title" id="ekyteModalTitle">Subir task no Ekyte</div>
    <div class="modal-task" id="ekyteTaskTitle"></div>
    <div class="modal-grid">
      <div class="field">
        <label for="ekyteWorkspace">Workspace</label>
        <select id="ekyteWorkspace"></select>
        <input class="ekyte-other-field hidden" id="ekyteWorkspaceOther" type="text" placeholder="ID do workspace">
      </div>
      <div class="field">
        <label for="ekyteProject">Projeto</label>
        <select id="ekyteProject"></select>
        <input class="ekyte-other-field hidden" id="ekyteProjectOther" type="text" placeholder="ID do projeto">
      </div>
      <div class="field">
        <label for="ekyteTaskType">Tipo de task</label>
        <select id="ekyteTaskType"></select>
        <input class="ekyte-other-field hidden" id="ekyteTaskTypeOther" type="text" placeholder="ID do tipo de task">
      </div>
      <div class="field">
        <label for="ekyteAssignee">Responsável</label>
        <select id="ekyteAssignee"></select>
        <input class="ekyte-other-field hidden" id="ekyteAssigneeOther" type="email" placeholder="e-mail do responsável">
      </div>
      <div class="field">
        <label for="ekyteDue">Prazo</label>
        <input id="ekyteDue" type="date">
      </div>
      <div class="field">
        <label for="ekyteMeetingDate">Data da reunião</label>
        <input id="ekyteMeetingDate" type="date">
      </div>
      <div class="field">
        <label for="ekyteRoutineTag">Tag de rotina</label>
        <select id="ekyteRoutineTag"></select>
      </div>
      <div class="field">
        <label for="ekyteWeekTag">Tag de semana</label>
        <select id="ekyteWeekTag"></select>
      </div>
    </div>
    <div class="modal-msg" id="ekyteMessage" aria-live="polite"></div>
    <div class="modal-actions">
      <button class="btn" id="ekyteCancelBtn" type="button">Cancelar</button>
      <button class="btn" id="ekyteQueueBtn" type="button">Salvar na fila</button>
      <button class="btn primary" id="ekyteCreateBtn" type="button">Criar no Ekyte</button>
    </div>
  </div>
</div>

<div class="modal-backdrop hidden" id="ekyteFlushModal" role="dialog" aria-modal="true" aria-labelledby="ekyteFlushTitle">
  <div class="modal-card wide">
    <div class="modal-title" id="ekyteFlushTitle">Fila Ekyte</div>
    <div class="modal-task">Revise as tasks pendentes antes de criar no Ekyte.</div>
    <div class="queue-tools">
      <label class="check-field"><input id="ekyteFlushSelectAll" type="checkbox" checked> Selecionar tudo</label>
      <span class="item-source" id="ekyteFlushSummary"></span>
    </div>
    <div class="queue-list" id="ekyteFlushList"></div>
    <div class="modal-msg" id="ekyteFlushMessage" aria-live="polite"></div>
    <div class="modal-actions">
      <button class="btn" id="ekyteFlushCancelBtn" type="button">Cancelar</button>
      <button class="btn" id="ekyteFlushValidateBtn" type="button">Validar fila</button>
      <button class="btn primary" id="ekyteFlushCreateBtn" type="button" disabled>Criar no Ekyte</button>
    </div>
  </div>
</div>

<div class="toast" id="toast" role="status" aria-live="polite"></div>

<script>
const DATA = __DATA_JSON__;
const SYSTEM_STATE = __SYSTEM_STATE_JSON__;
const USER_CONFIG = __USER_CONFIG_JSON__;
const EKYTE_CONFIG = SYSTEM_STATE.ekyte_config || {};
const sprint = DATA.sprints[DATA.meta.currentSprint];
const storageKey = `todos-done-v2:${DATA.meta.currentSprint}`;
const historyKey = `todos-history-v1:${DATA.meta.currentSprint}`;
const followKey = `todos-follow-v1:${DATA.meta.currentSprint}`;
const doneState = JSON.parse(localStorage.getItem(storageKey) || localStorage.getItem('todos-done-v2') || '{}');
const taskHistory = JSON.parse(localStorage.getItem(historyKey) || '{}');
let followList = JSON.parse(localStorage.getItem(followKey) || '[]');
if (!Array.isArray(followList)) followList = [];
const collapsedState = JSON.parse(localStorage.getItem(`todos-collapsed:${DATA.meta.currentSprint}`) || '{}');
const hideDoneState = JSON.parse(localStorage.getItem(`todos-hide-done:${DATA.meta.currentSprint}`) || '{}');
let clientPendingEkyteQueue = Array.isArray(SYSTEM_STATE.ekyte_pending) ? [...SYSTEM_STATE.ekyte_pending] : [];
const clientPendingEkyteIds = new Set(clientPendingEkyteQueue.map(i => i.item_id));
const filters = { scope: 'all', category: 'all', query: '' };
let pendingCompletion = null;
let pendingEkyte = null;
let flushSelectedIds = new Set(clientPendingEkyteQueue.map(i => i.item_id).filter(Boolean));
let flushValidationRows = null;
let serverOnline = null;
const LOCAL_SERVER_BASE = 'http://127.0.0.1:8787';

const $ = id => document.getElementById(id);
const escMap = {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'};
function esc(v) { return String(v ?? '').replace(/[&<>"']/g, c => escMap[c]); }
function attr(v) { return esc(v).replace(/`/g,'&#96;'); }
function allItems() { return sprint.categories.flatMap(c => c.items.map(i => ({category:c, item:i}))); }
function rows(v) { return Array.isArray(v) ? v : []; }
const OTHER_ID = '__other__';
const OTHER_OPTION = {id: OTHER_ID, name: 'Outros (informar ID)', is_other: true};
const OTHER_EMAIL_OPTION = {id: OTHER_ID, name: 'Outros (informar e-mail)', email: '', is_other: true};
function withOtherOptions(list, emailField=false) {
  const base = rows(list).filter(r => !r.is_other && r.id !== OTHER_ID);
  return [...base, emailField ? OTHER_EMAIL_OPTION : OTHER_OPTION];
}
function toggleEkyteOtherFields() {
  const pairs = [
    ['ekyteWorkspace','ekyteWorkspaceOther'],
    ['ekyteProject','ekyteProjectOther'],
    ['ekyteTaskType','ekyteTaskTypeOther'],
    ['ekyteAssignee','ekyteAssigneeOther'],
  ];
  pairs.forEach(([selId, inpId]) => {
    const inp = $(inpId);
    if (!inp) return;
    const show = $(selId)?.value === OTHER_ID;
    inp.classList.toggle('hidden', !show);
  });
}
function resolveSelectValue(selectId, otherInputId) {
  const sel = $(selectId);
  if (!sel) return '';
  if (sel.value === OTHER_ID) return String($(otherInputId)?.value || '').trim();
  return sel.value || '';
}
function resolveSelectLabel(selectId, otherInputId) {
  const sel = $(selectId);
  if (!sel) return '';
  if (sel.value === OTHER_ID) {
    const manual = String($(otherInputId)?.value || '').trim();
    return manual ? `Outros: ${manual}` : 'Outros';
  }
  return selectedLabel(selectId);
}
function sameId(a,b) { return String(a ?? '') === String(b ?? ''); }
function norm(v) { return String(v||'').normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim(); }
function byId(list, id) { return rows(list).find(r => sameId(r.id,id)); }
function option(value, label, selected, extra='') { return `<option value="${attr(value)}"${selected?' selected':''}${extra}>${esc(label||value||'-')}</option>`; }
function selectedLabel(selectId) { const opt=$(selectId)?.selectedOptions?.[0]; return opt ? opt.textContent : ''; }
function selectedData(selectId, key) { const opt=$(selectId)?.selectedOptions?.[0]; return opt?.dataset?.[key] || ''; }
function workspaceRows() { return rows(EKYTE_CONFIG.workspaces); }
function defaultWorkspaceId() { return EKYTE_CONFIG.default_workspace_id || workspaceRows()[0]?.id || ''; }
function projectsForWorkspace(workspaceId) { return rows(byId(workspaceRows(), workspaceId)?.projects); }
function taskTypesForWorkspace(workspaceId) {
  const workspaceTypes = rows(byId(workspaceRows(), workspaceId)?.task_types);
  return workspaceTypes.length ? workspaceTypes : rows(EKYTE_CONFIG.task_types);
}
function defaultProjectId(workspaceId) {
  const projects = projectsForWorkspace(workspaceId);
  const qProject = projects.find(p => /\\bq[1-4]\\b|trimestr/i.test(norm(p.name)));
  return (qProject || projects[0] || {}).id || '';
}
function defaultTaskTypeId(workspaceId) {
  const types = taskTypesForWorkspace(workspaceId);
  return EKYTE_CONFIG.default_task_type_id || (types.find(t => sameId(t.id,'68301')) || types[0] || {}).id || '';
}
function assigneeRows() { return rows(EKYTE_CONFIG.assignees); }
function defaultAssigneeEmail() { return EKYTE_CONFIG.default_assignee_email || USER_CONFIG.user?.email || 'jefferson.vieira@v4company.com'; }
function tagRows(key, fallback) { const configured=rows(EKYTE_CONFIG[key]); return configured.length ? configured : fallback.map(name=>({name,id:''})); }
function routineTagRows() { return tagRows('routine_tags',['AÇÃO GERENCIAL','SPRINT GROWTH','WEEKLY EXPANSÃO','ALINHAMENTO COMITÊ','QUALITY CONTROL','WAR']); }
function weekTagRows() { return tagRows('week_tags',Array.from({length:52},(_,i)=>`SEMANA ${String(i+1).padStart(2,'0')}`)); }
function parseDateFromText(value) {
  const text = String(value || '');
  let m = text.match(/\\b(20\\d{2})[-_/](\\d{2})[-_/](\\d{2})\\b/);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  m = text.match(/\\b(\\d{2})\\/(\\d{2})\\/(20\\d{2})\\b/);
  if (m) return `${m[3]}-${m[2]}-${m[1]}`;
  const d = new Date(text);
  if (!Number.isNaN(d.getTime())) return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,10);
  return '';
}
function meetingDateForClient(item, entry={}) {
  return entry.meeting_date || item.meeting_date || parseDateFromText(item.source) || parseDateFromText(item.auto_added_at) || parseDateFromText(entry.queued_at) || localIsoPlus(0);
}
function isoWeek(dateStr) {
  const d = new Date(`${dateStr}T12:00:00`);
  if (Number.isNaN(d.getTime())) return 1;
  d.setHours(0,0,0,0);
  d.setDate(d.getDate() + 3 - ((d.getDay()+6)%7));
  const week1 = new Date(d.getFullYear(),0,4);
  return 1 + Math.round(((d - week1) / 86400000 - 3 + ((week1.getDay()+6)%7)) / 7);
}
function weekTagForClient(dateStr) {
  const week = Math.max(1, Math.min(52, isoWeek(dateStr)));
  return `SEMANA ${String(week).padStart(2,'0')}`;
}
function inferRoutineTagClient(...parts) {
  const text = ` ${norm(parts.join(' '))} `;
  const patterns = [
    ['SPRINT GROWTH',['sprint growth']],
    ['QUALITY CONTROL',['quality control','quality check','controle qualidade','qc']],
    ['ALINHAMENTO COMITÊ',['alinhamento comite','comite ops','comite','alinhamento']],
    ['WAR',[' war ','sala war','war room']],
    ['WEEKLY EXPANSÃO',['weekly expansao','weekly expansion','expansao']],
    ['AÇÃO GERENCIAL',['acao gerencial','gerencial','daily coordenacao','daily gerencia']],
  ];
  for (const [tag, needles] of patterns) if (needles.some(n => text.includes(n))) return tag;
  return '';
}

function endpointCandidates(path) {
  const n = path.startsWith('/') ? path : `/${path}`;
  const local = `${LOCAL_SERVER_BASE}${n}`;
  if (window.location.protocol === 'file:') return [local, n];
  if (window.location.origin === LOCAL_SERVER_BASE) return [n];
  return [n, local];
}
async function postJson(path, payload) {
  let lastErr = null;
  for (const ep of endpointCandidates(path)) {
    try {
      const r = await fetch(ep, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
      const text = await r.text();
      const data = text ? JSON.parse(text) : {};
      if (!r.ok || data.ok === false) throw new Error(data.error || `HTTP ${r.status}`);
      return data;
    } catch(e) { lastErr = e; }
  }
  throw lastErr || new Error('Servidor local indisponível');
}
async function checkServer() {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 2000);
    const r = await fetch(`${LOCAL_SERVER_BASE}/api/status`, {signal: ctrl.signal});
    clearTimeout(t);
    serverOnline = r.ok;
  } catch { serverOnline = false; }
  renderSystemStrip();
}
function syncPendingEkyteState(queue) {
  clientPendingEkyteQueue = Array.isArray(queue) ? queue : [];
  clientPendingEkyteIds.clear();
  clientPendingEkyteQueue.forEach(i => { if (i?.item_id) clientPendingEkyteIds.add(i.item_id); });
}
function isDone(item) {
  return Object.prototype.hasOwnProperty.call(doneState, item.id) ? !!doneState[item.id] : item.done === true;
}
function setDone(id, value) {
  doneState[id] = value;
  localStorage.setItem(storageKey, JSON.stringify(doneState));
  localStorage.setItem('todos-done-v2', JSON.stringify(doneState));
}
function saveTaskHistory() { localStorage.setItem(historyKey, JSON.stringify(taskHistory)); }
function saveFollowList() { localStorage.setItem(followKey, JSON.stringify(followList)); }
function removeFromFollow(itemId) {
  const before = followList.length;
  followList = followList.filter(f => f.item_id !== itemId);
  if (followList.length !== before) saveFollowList();
}
let pendingFollowDismiss = null;
function openFollowDismiss(followEntry) {
  pendingFollowDismiss = followEntry;
  $('followDismissTaskTitle').textContent = followEntry.title || '';
  $('followDismissNote').value = '';
  $('followDismissModal').classList.remove('hidden');
  setTimeout(() => $('followDismissNote').focus(), 30);
}
function cancelFollowDismiss() {
  pendingFollowDismiss = null;
  $('followDismissModal').classList.add('hidden');
}
function finishFollowDismiss(withNote) {
  if (!pendingFollowDismiss) return;
  const note = withNote ? $('followDismissNote').value.trim() : '';
  const itemId = pendingFollowDismiss.item_id;
  if (note && itemId) {
    if (!Array.isArray(taskHistory[itemId])) taskHistory[itemId] = [];
    taskHistory[itemId].push({
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      at: new Date().toISOString(), status: 'follow_done', note,
      title: pendingFollowDismiss.title || '',
      source: pendingFollowDismiss.source || '',
      category_id: pendingFollowDismiss.category_id || '',
      category_name: pendingFollowDismiss.category_name || '',
    });
    saveTaskHistory();
  }
  removeFromFollow(itemId);
  pendingFollowDismiss = null;
  $('followDismissModal').classList.add('hidden');
  render();
  showToast(note ? 'Follow concluído com nota' : 'Follow concluído', 'ok');
}
function addToFollow(entry, note) {
  const {category, item} = entry;
  if (followList.some(f => f.item_id === item.id)) return;
  followList.push({
    item_id: item.id, title: item.title,
    category_id: category.id, category_name: category.name || category.id,
    source: item.source || '', note: note || '',
    completed_at: new Date().toISOString(), created_at: item.auto_added_at || ''
  });
  saveFollowList();
}
function fmtDate(v) {
  try { return new Intl.DateTimeFormat('pt-BR',{day:'2-digit',month:'2-digit',year:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(v)); }
  catch { return v || '-'; }
}
function fmtMonth(iso) {
  try { return new Intl.DateTimeFormat('pt-BR',{month:'long',year:'numeric'}).format(new Date(iso)); }
  catch { return iso ? iso.slice(0,7) : '-'; }
}
function recordHistory(entry, status, note) {
  const {category, item} = entry;
  const ev = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    at: new Date().toISOString(), status, note: (note||'').trim(),
    title: item.title, source: item.source,
    category_id: category.id, category_name: category.name || category.id
  };
  if (!Array.isArray(taskHistory[item.id])) taskHistory[item.id] = [];
  taskHistory[item.id].push(ev);
  saveTaskHistory();
  return ev;
}
function removeLastHistory(itemId) {
  const arr = taskHistory[itemId];
  if (!Array.isArray(arr) || !arr.length) return;
  arr.pop();
  if (!arr.length) delete taskHistory[itemId];
  saveTaskHistory();
}
function updateHistoryNote(itemId, eventId, note) {
  const ev = (taskHistory[itemId]||[]).find(e => e.id === eventId);
  if (ev) { ev.note = (note||'').trim(); saveTaskHistory(); }
}
function histEntries(item) { return Array.isArray(taskHistory[item.id]) ? taskHistory[item.id] : []; }
function renderItemHistory(item, done) {
  if (!done) return '';
  const entries = histEntries(item);
  if (!entries.length) return '';
  return `<div class="history-log">${[...entries].slice(-3).reverse().map(e => {
    const cls = e.status==='reopened'?'reopened':'';
    const lbl = e.status==='reopened'?'Reaberta':'Concluída';
    return `<div class="history-entry ${cls}"><strong>${lbl}</strong> · ${esc(fmtDate(e.at))}${e.note?`<div class="history-note">${esc(e.note)}</div>`:''}</div>`;
  }).join('')}</div>`;
}
function openModal(entry, eventId) {
  pendingCompletion = {itemId: entry.item.id, eventId, entry};
  $('completionTaskTitle').textContent = entry.item.title || '';
  $('completionNote').value = '';
  $('completionFollow').checked = false;
  $('completionModal').classList.remove('hidden');
  setTimeout(() => $('completionNote').focus(), 30);
}
function cancelCompletion() {
  if (!pendingCompletion) return;
  setDone(pendingCompletion.itemId, false);
  removeLastHistory(pendingCompletion.itemId);
  pendingCompletion = null;
  $('completionModal').classList.add('hidden');
  render();
}
function finishCompletion(withNote) {
  if (!pendingCompletion) return;
  const note = withNote ? $('completionNote').value : '';
  const follow = $('completionFollow').checked;
  if (note.trim()) updateHistoryNote(pendingCompletion.itemId, pendingCompletion.eventId, note);
  if (follow) addToFollow(pendingCompletion.entry, note.trim());
  const msg = follow ? 'Task concluída e adicionada ao Follow' : (note.trim() ? 'Anotação salva no histórico' : 'Task concluída');
  const kind = follow ? 'info' : 'ok';
  pendingCompletion = null;
  $('completionModal').classList.add('hidden');
  render();
  showToast(msg, kind);
}
function toggleDone(entry) {
  const next = !isDone(entry.item);
  setDone(entry.item.id, next);
  if (next) {
    const ev = recordHistory(entry, 'done', '');
    render();
    openModal(entry, ev.id);
    return;
  }
  recordHistory(entry, 'reopened', '');
  render();
  showToast('Task reaberta', 'warn');
}
function matchQ(q, fields) {
  if (!q) return true;
  const ql = q.toLowerCase();
  return fields.some(f => f && String(f).toLowerCase().includes(ql));
}
function itemMatches(entry) {
  const {category, item} = entry;
  const done = isDone(item);
  const histText = histEntries(item).map(e => e.note).filter(Boolean).join(' ');
  const fields = [item.title, item.context, item.source, item.source_quote, item.suggested_action, histText];
  if (filters.category !== 'all' && category.id !== filters.category) return false;
  if (!matchQ(filters.query, fields)) return false;
  if (filters.scope === 'urgent' && item.priority !== 'urgente') return false;
  if (filters.scope === 'review' && !item.review_needed) return false;
  if (filters.scope === 'alerts' && category.id !== 'alertas') return false;
  if (filters.scope === 'done' && !done) return false;
  if (filters.scope === 'open' && done) return false;
  return true;
}
function filteredByCategory(cat) {
  const hide = hideDoneState[cat.id] === true && filters.scope !== 'done';
  return cat.items
    .filter(item => !(hide && isDone(item)))
    .map(item => ({category:cat, item}))
    .filter(itemMatches);
}
function counts() {
  const all = allItems();
  const total = all.length;
  const done = all.filter(({item}) => isDone(item)).length;
  return {
    total, done, open: total-done,
    urgent: all.filter(({item}) => item.priority==='urgente' && !isDone(item)).length,
    review: all.filter(({item}) => item.review_needed && !isDone(item)).length,
    alerts: all.filter(({category,item}) => category.id==='alertas' && !isDone(item)).length,
    follow: followList.length
  };
}
function renderHeader() {
  const meta = DATA.meta || {};
  const sync = SYSTEM_STATE.last_sync;
  const lastSync = sync?.last_sync_at || meta.lastUpdated || '—';
  const alertCount = SYSTEM_STATE.last_alerts?.active_alerts ? Object.keys(SYSTEM_STATE.last_alerts.active_alerts).length : null;
  $('headerMeta').textContent = `Sprint ${meta.currentSprint||''} · Sync ${lastSync}${alertCount!==null?` · ${alertCount} alertas`:''}`;
  const flush = $('flushEkyteBtn');
  if (flush) { const n=clientPendingEkyteQueue.length; flush.textContent=`Fila Ekyte (${n})`; flush.classList.toggle('hidden',n===0); }
}
function renderStats() {
  const c = counts();
  const statData = [
    ['Alertas',  c.alerts,  'alerts'],
    ['Abertos',  c.open,    'open'],
    ['Urgentes', c.urgent,  'urgent'],
    ['Verificar',c.review,  'review'],
    ['Feitos',   c.done,    'history'],
    ['Follow',   c.follow,  'follow'],
  ];
  const isFiltered = filters.scope !== 'all' || filters.category !== 'all' || filters.query;
  $('clearFiltersBtn').classList.toggle('hidden', !isFiltered);
  $('stats').innerHTML = statData.map(([label,value,scope]) => {
    const isActive = filters.scope === scope;
    return `<button class="stat-btn${isActive?' active':''}" type="button" data-scope="${attr(scope)}" title="${label}: ${value}">
      <div class="stat-value">${value}</div>
      <div class="stat-label">${label}</div>
    </button>`;
  }).join('');
}
function chipBtn(label, value, active, count, kind) {
  const short = label.length > 22 ? label.slice(0,20)+'…' : label;
  return `<button class="chip${active?' active':''}" type="button" data-${kind}="${attr(value)}">${esc(short)}${count!==undefined?`<span class="count"> ${count}</span>`:''}</button>`;
}
function renderFilterBar() {
  const c = counts();
  const isSpecial = ['history','follow'].includes(filters.scope);
  const fb = $('filterBar');
  if (isSpecial) { fb.innerHTML = ''; fb.style.display = 'none'; return; }
  fb.style.display = '';
  const pct = c.total ? Math.round((c.done/c.total)*100) : 0;
  const chips = [
    chipBtn('Tudo','all',filters.category==='all',undefined,'category'),
    ...sprint.categories.map(cat => {
      const open = cat.items.filter(i => !isDone(i)).length;
      return chipBtn(cat.name||cat.id, cat.id, filters.category===cat.id, open, 'category');
    })
  ].join('');
  fb.innerHTML = `<div class="chips">${chips}</div><div class="progress-inline"><div class="progress-track-sm"><div class="progress-fill-sm" style="width:${pct}%"></div></div>${c.done}/${c.total}</div>`;
}
function mkTag(label, cls) { return `<span class="tag ${cls||''}">${esc(label)}</span>`; }
function mkTagLink(label, cls, href) { return `<a class="tag ${cls||''}" href="${attr(href)}" target="_blank" rel="noreferrer">${esc(label)}</a>`; }
function ekyteUrl(item) {
  return item.ekaite_task_url||item.ekyte_task_url||item.ekaite_url||item.ekyte_url||
    (item.ekaite_task_id?`https://app.ekyte.com/#/tasks/list/${encodeURIComponent(item.ekaite_task_id)}/edit`:'');
}
function canQueueEkyte(item) {
  if (item.ekaite_task_id||clientPendingEkyteIds.has(item.id)||item.review_needed) return false;
  return item.priority==='urgente' && item.confidence==='alta';
}
function renderItem(category, item) {
  const done = isDone(item);
  const ev = item.alert_evidence || {};
  const pCls = item.priority==='urgente'?'urgente':item.priority==='recorrente'?'recorrente':'normal';
  const confTag = item.confidence ? mkTag(item.confidence==='alta'?'Conf. alta':'Verificar', item.confidence==='alta'?'alta':'media') : '';
  const reviewTag = item.review_needed ? mkTag('Revisar','review') : '';
  const evidTag = ev.band ? mkTag(ev.band,'alert') : '';
  const checkinTag = (ev.days_since||ev.days_since_checkin) ? mkTag(`${ev.days_since||ev.days_since_checkin}d s/checkin`,'review') : '';
  const pending = item.ekaite_pending || clientPendingEkyteIds.has(item.id);
  const ekyteTagLink = item.ekaite_task_id
    ? mkTagLink(`✓ Ekyte #${item.ekaite_task_id}`,'ekyte-ok',ekyteUrl(item))
    : pending ? mkTag('Ekyte pendente','ekyte-pending') : '';
  const noTagHint = item.ekyte_needs_manual_tag ? item.ekyte_tag_hint || 'adicionar tags manualmente' : '';
  const ekyteTag = item.ekyte_needs_manual_tag
    ? `${ekyteTagLink}${mkTag('Ekyte sem tag · ' + noTagHint, 'ekyte-notag')}`
    : ekyteTagLink;
  const ekyteBtn = canQueueEkyte(item) ? `<button class="mini-btn" type="button" data-ekyte="${attr(item.id)}">↑ Ekyte</button>` : '';
  const followTag = followList.some(f => f.item_id===item.id) ? mkTag('Follow','follow') : '';
  const evLink = ev.source_url ? `<a class="item-source" href="${attr(ev.source_url)}" target="_blank" rel="noreferrer">evidência ↗</a>` : '';
  const quote = item.source_quote ? `<div class="item-quote">"${esc(item.source_quote)}"${item.source_timestamp?` · ${esc(item.source_timestamp)}`:''}</div>` : '';
  const action = item.suggested_action ? `<div class="item-action">→ ${esc(item.suggested_action)}</div>` : '';
  const hist = renderItemHistory(item, done);
  return `<article class="item${done?' done':''}${category.id==='alertas'?' alert-item':''}" id="item-${attr(item.id)}">
  <div class="item-check-col">
    <button class="checkbox${done?' checked':''}" type="button" data-toggle="${attr(item.id)}" aria-label="${done?'Reabrir':'Concluir'} task"></button>
  </div>
  <div class="item-body">
    <div class="item-row1">
      <span class="item-title">${esc(item.title)}</span>
      ${mkTag(item.priority, pCls)}${ekyteTag}${followTag}
    </div>
    ${item.context?`<div class="item-context">${esc(item.context)}</div>`:''}
    ${quote}${action}${hist}
    <div class="item-meta">${confTag}${reviewTag}${evidTag}${checkinTag}${ekyteBtn}<span class="item-source">${esc(item.source||'')}</span>${evLink}</div>
  </div>
</article>`;
}
function renderCategories() {
  const isSpecial = ['history','follow'].includes(filters.scope);
  $('categories').style.display = isSpecial ? 'none' : '';
  if (isSpecial) return;
  const html = sprint.categories.map(cat => {
    const items = filteredByCategory(cat);
    if (filters.category!=='all' && cat.id!==filters.category && items.length===0) return '';
    if (items.length===0 && (filters.query||filters.scope!=='all')) return '';
    const done = cat.items.filter(i => isDone(i)).length;
    const open = cat.items.length - done;
    const collapsed = collapsedState[cat.id]===true;
    const hide = hideDoneState[cat.id]===true;
    const meta = [`${items.length} visíveis`,`${open} abertos`];
    if (hide&&done>0) meta.push(`${done} feitos ocultos`);
    const empty = hide&&done>0 ? 'Feitos ocultos neste bloco' : 'Nenhum item nesta visão';
    return `<section class="category${cat.id==='alertas'?' alertas':''}">
  <div class="category-head">
    <button class="category-main" type="button" data-collapse="${attr(cat.id)}">
      <div><div class="category-name">${esc(cat.name||cat.id)}</div><div class="category-meta">${meta.join(' · ')}</div></div>
    </button>
    <div class="category-actions">
      <button class="hide-done-btn${hide?' active':''}" type="button" data-hide-done="${attr(cat.id)}">${hide?`Mostrar feitos (${done})`:`Ocultar feitos (${done})`}</button>
      <span class="badge${cat.id==='alertas'&&open>0?' risk':''}">${open}</span>
    </div>
  </div>
  <div class="category-body${collapsed?' collapsed':''}">
    ${items.length?items.map(({item})=>renderItem(cat,item)).join(''):`<div class="empty-state">${empty}</div>`}
  </div>
</section>`;
  }).join('');
  $('categories').innerHTML = html || '<div class="empty-state">Nenhum item encontrado</div>';
}
function renderHistoryView() {
  const view = $('historyView');
  if (filters.scope !== 'history') { view.classList.remove('visible'); return; }
  view.classList.add('visible');
  const q = filters.query.toLowerCase();
  const events = [];
  Object.values(taskHistory).forEach(arr => {
    if (!Array.isArray(arr)) return;
    arr.forEach(e => {
      if (e.status !== 'done') return;
      if (q && !['title','note','source','category_name'].some(k => e[k] && String(e[k]).toLowerCase().includes(q))) return;
      events.push(e);
    });
  });
  events.sort((a,b) => (b.at||'').localeCompare(a.at||''));
  if (!events.length) { view.innerHTML=`<div class="empty-state">Nenhuma task concluída${q?' para esta busca':''} ainda.</div>`; return; }
  const months = {};
  events.forEach(e => { const k=e.at?e.at.slice(0,7):'desconhecido'; (months[k]=months[k]||[]).push(e); });
  view.innerHTML = Object.keys(months).sort((a,b)=>b.localeCompare(a)).map(k =>
    `<div class="month-group">
  <div class="month-title">${esc(fmtMonth(k+'-01'))} <span style="opacity:.5;font-weight:400">${months[k].length} task${months[k].length!==1?'s':''}</span></div>
  ${months[k].map(e=>`<div class="hist-card">
    <div class="hist-card-title">${esc(e.title||'-')}</div>
    <div class="hist-card-meta"><span>${esc(e.category_name||e.category_id||'-')}</span>${e.source?`<span>·</span><span>${esc(e.source)}</span>`:''}<span>·</span><span>${esc(fmtDate(e.at))}</span></div>
    ${e.note?`<div class="hist-card-note">${esc(e.note)}</div>`:''}
  </div>`).join('')}
</div>`).join('');
}
function renderFollowView() {
  const view = $('followView');
  if (filters.scope !== 'follow') { view.classList.remove('visible'); return; }
  view.classList.add('visible');
  const q = filters.query.toLowerCase();
  const items = [...followList].reverse().filter(f => !q || ['title','note','source','category_name'].some(k => f[k] && String(f[k]).toLowerCase().includes(q)));
  if (!items.length) { view.innerHTML=`<div class="empty-state">Nenhuma task em Follow${q?' para esta busca':''}.</div>`; return; }
  view.innerHTML = items.map(f=>`<div class="follow-card" data-follow-id="${attr(f.item_id)}">
  <div class="follow-card-title">${esc(f.title||'-')}</div>
  <div class="follow-card-meta"><span>${esc(f.category_name||f.category_id||'-')}</span>${f.source?`<span>·</span><span>${esc(f.source)}</span>`:''}${f.completed_at?`<span>·</span><span>Concluída ${esc(fmtDate(f.completed_at))}</span>`:''}</div>
  ${f.note?`<div class="follow-card-note">${esc(f.note)}</div>`:''}
  <div class="follow-card-actions">
    <button class="btn primary" type="button" data-follow-done="${attr(f.item_id)}">Concluir follow</button>
  </div>
</div>`).join('');
}
function renderSystemStrip() {
  const sync = SYSTEM_STATE.last_sync || {};
  const trigger = SYSTEM_STATE.refresh_trigger;
  const sLabel = serverOnline===null ? '…' : serverOnline ? 'Servidor local OK' : 'Sem servidor — abra via http://127.0.0.1:8787';
  const sCls = serverOnline===null ? '' : serverOnline ? 'server-ok' : 'server-off';
  $('systemStrip').innerHTML = [
    {l:'Gerado', v:SYSTEM_STATE.generated_at||'—', c:''},
    {l:'Último sync', v:sync.last_sync_at||'—', c:''},
    {l:'Fila Ekyte', v:String(clientPendingEkyteQueue.length), c:''},
    {l:'Trigger', v:trigger?`${trigger.from} → ${trigger.to}`:'nenhum', c:''},
    {l:'Servidor', v:sLabel, c:sCls},
  ].map(r=>`<div class="sys-item${r.c?' '+r.c:''}">${esc(r.l)}<strong>${esc(r.v)}</strong></div>`).join('');
}
function renderErrors() {
  const errs = Array.isArray(SYSTEM_STATE.refresh_errors) ? SYSTEM_STATE.refresh_errors : [];
  const el = $('errorBanner');
  if (!errs.length) { el.classList.remove('visible'); el.innerHTML=''; return; }
  el.classList.add('visible');
  el.innerHTML=`<div><div class="status-title">${errs.length} erro(s) de atualização</div><div class="status-detail">${esc(errs[0].file_name||errs[0].motivo||'Verifique .todos/refresh-errors.json')}</div></div><button class="btn danger" type="button" id="retryForceBtn">Retentar</button>`;
}
function render() {
  renderHeader(); renderStats(); renderFilterBar();
  renderCategories(); renderHistoryView(); renderFollowView();
  renderSystemStrip(); renderErrors();
}
function showToast(msg, kind) {
  const t = $('toast');
  t.className = `toast visible ${kind||'ok'}`;
  t.textContent = msg;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => t.classList.remove('visible'), 4500);
}
function setPresetDates() {
  const p = $('refreshPreset').value;
  const today = new Date();
  const iso = d => { const c=new Date(d.getTime()-d.getTimezoneOffset()*60000); return c.toISOString().slice(0,10); };
  const from=new Date(today), to=new Date(today);
  if (p==='yesterday') { from.setDate(today.getDate()-1); to.setDate(today.getDate()-1); }
  else if (p==='last7') { from.setDate(today.getDate()-6); }
  if (p!=='custom') { $('refreshFrom').value=iso(from); $('refreshTo').value=iso(to); }
}
async function copyText(v) {
  try { await navigator.clipboard.writeText(v); } catch {
    const ta=document.createElement('textarea'); ta.value=v;
    document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove();
  }
}
function downloadJson(filename, payload) {
  const blob=new Blob([JSON.stringify(payload,null,2)+'\\n'],{type:'application/json'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a'); a.href=url; a.download=filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function createTrigger(forceOverride) {
  const payload={from:$('refreshFrom').value,to:$('refreshTo').value,
    force_reprocess:forceOverride===true?true:$('refreshForce').checked,preset:$('refreshPreset').value};
  const msg=$('refreshMessage');
  if (!payload.from||!payload.to) { msg.textContent='Selecione o período.'; msg.className='panel-msg err'; return; }
  try {
    const r=await postJson('/api/refresh',payload);
    if (!r.ok) throw new Error(r.error||'Falha');
    msg.textContent=`Trigger criado: ${r.trigger.from} → ${r.trigger.to}`; msg.className='panel-msg ok';
    showToast('Trigger criado em .todos/refresh-trigger.json');
  } catch {
    const cmd=`/atualiza-todos\nrange: ${payload.from} -> ${payload.to}\nforce_reprocess: ${payload.force_reprocess}\npreset: ${payload.preset}`;
    await copyText(cmd);
    msg.textContent='Servidor indisponível. Abra via http://127.0.0.1:8787 ou cole o comando copiado no Claude.';
    msg.className='panel-msg err';
    showToast('Comando copiado — cole no Claude Code','err');
  }
}
function populateManualCategories() {
  const s=$('manualCategory');
  s.innerHTML=sprint.categories.map(c=>`<option value="${attr(c.id)}">${esc(c.name||c.id)}</option>`).join('');
  if (sprint.categories.some(c=>c.id==='projetos')) s.value='projetos';
}
function resetManualForm() {
  ['manualTitle','manualContext','manualSource'].forEach(id=>$(id).value='');
  $('manualPriority').value='normal'; $('manualConfidence').value='alta'; $('manualReview').checked=false;
}
async function createManualTask() {
  const payload={category_id:$('manualCategory').value,title:$('manualTitle').value.trim(),
    context:$('manualContext').value.trim(),priority:$('manualPriority').value,
    confidence:$('manualConfidence').value,review_needed:$('manualReview').checked,source:$('manualSource').value.trim()};
  const msg=$('manualMessage');
  if (!payload.title) { msg.textContent='Informe o título.'; msg.className='panel-msg err'; return; }
  try {
    const r=await postJson('/api/manual-task',payload);
    if (!r.ok) throw new Error(r.error||'Falha');
    const cat=sprint.categories.find(c=>c.id===r.category_id);
    if (cat&&r.item) cat.items.push(r.item);
    collapsedState[r.category_id]=false;
    localStorage.setItem(`todos-collapsed:${DATA.meta.currentSprint}`,JSON.stringify(collapsedState));
    $('manualPanel').classList.remove('visible'); resetManualForm(); showToast('Task adicionada'); render();
    setTimeout(()=>{ const el=document.getElementById(`item-${r.item.id}`); if(el) el.scrollIntoView({behavior:'smooth',block:'center'}); },60);
  } catch {
    await copyText(`/todos-add-manual\n${JSON.stringify(payload,null,2)}`);
    msg.textContent='Servidor indisponível. Dados copiados — cole no Claude Code.'; msg.className='panel-msg err';
    showToast('Dados copiados','err');
  }
}
function localIsoPlus(days) {
  const d=new Date(); d.setDate(d.getDate()+days);
  const c=new Date(d.getTime()-d.getTimezoneOffset()*60000); return c.toISOString().slice(0,10);
}
function buildEkyteEntry(category, item, overrides={}) {
  const workspaceId = overrides.workspace_id || item.workspace_id || item.ekyte_workspace_id || defaultWorkspaceId();
  const projectId = overrides.project_id || item.project_id || item.ekyte_project_id || defaultProjectId(workspaceId);
  const taskTypeId = overrides.task_type_id || item.task_type_id || item.ekyte_task_type_id || defaultTaskTypeId(workspaceId);
  const assigneeEmail = overrides.assignee_email || item.assignee_email || defaultAssigneeEmail();
  const meetingDate = overrides.meeting_date || meetingDateForClient(item, overrides);
  const routineName = overrides.routine_tag_name || inferRoutineTagClient(item.source,item.title,category.name);
  const weekName = overrides.week_tag_name || weekTagForClient(meetingDate);
  const routine = routineTagRows().find(t => norm(t.name)===norm(routineName)) || {};
  const week = weekTagRows().find(t => norm(t.name)===norm(weekName)) || {};
  return {item_id:item.id,sprint:DATA.meta.currentSprint,category_id:category.id,
    category_name:category.name||category.id,workspace_id:workspaceId,
    workspace_label:overrides.workspace_label||byId(workspaceRows(),workspaceId)?.name||(USER_CONFIG.user?.full_name?'Coord. '+USER_CONFIG.user.full_name:'Coord. Jefferson Vieira'),
    project_id:projectId,project_name:overrides.project_name||byId(projectsForWorkspace(workspaceId),projectId)?.name||'',
    task_type_id:taskTypeId,task_type_name:overrides.task_type_name||byId(taskTypesForWorkspace(workspaceId),taskTypeId)?.name||'',
    assignee_email:assigneeEmail,assignee_name:overrides.assignee_name||assigneeRows().find(a=>String(a.email).toLowerCase()===String(assigneeEmail).toLowerCase())?.name||assigneeEmail,
    routine_tag_name:routineName,routine_tag_id:overrides.routine_tag_id||routine.id||'',
    week_tag_name:weekName,week_tag_id:overrides.week_tag_id||week.id||'',
    meeting_date:meetingDate,
    title:item.title,description:`${item.context||''}\n\nOrigem: ${item.source||'-'}`,
    due_date:overrides.due_date||localIsoPlus(2),priority:'urgente',source:item.source||'',queued_at:overrides.queued_at||new Date().toISOString()};
}
async function readEkyteQueue() {
  try { const r=await fetch('.todos/ekyte-pending.json',{cache:'no-store'}); if(!r.ok) throw 0; const p=await r.json(); return Array.isArray(p)?p:[]; }
  catch { return [...clientPendingEkyteQueue]; }
}
async function tryWriteQueue(queue) {
  try { const r=await postJson('/write-json',{path:'.todos/ekyte-pending.json',data:queue}); return !!r.ok; }
  catch { return false; }
}
function fillSelect(selectId, list, selectedValue, emptyLabel='') {
  const empty = emptyLabel ? option('', emptyLabel, !selectedValue) : '';
  $(selectId).innerHTML = empty + rows(list).map(row => option(row.id ?? row.name, row.name || row.email || row.id, sameId(row.id ?? row.name, selectedValue), row.id?` data-id="${attr(row.id)}"`:'')).join('');
  toggleEkyteOtherFields();
}
function refreshEkyteProjectAndType(draft={}) {
  const workspaceId = $('ekyteWorkspace').value === OTHER_ID
    ? resolveSelectValue('ekyteWorkspace', 'ekyteWorkspaceOther')
    : $('ekyteWorkspace').value;
  const projects = withOtherOptions(projectsForWorkspace(workspaceId));
  const types = withOtherOptions(taskTypesForWorkspace(workspaceId));
  fillSelect('ekyteProject', projects, draft.project_id || defaultProjectId(workspaceId), 'Selecione');
  fillSelect('ekyteTaskType', types, draft.task_type_id || defaultTaskTypeId(workspaceId), 'Selecione');
  updateEkyteCreateState();
}
function fillEkyteModal(entry, draft) {
  $('ekyteTaskTitle').textContent = draft.title || entry.item.title || '';
  fillSelect('ekyteWorkspace', withOtherOptions(EKYTE_CONFIG.workspaces), draft.workspace_id || defaultWorkspaceId(), 'Selecione');
  refreshEkyteProjectAndType(draft);
  const assignees = withOtherOptions(assigneeRows(), true).map(a=>({id:a.email || a.id,name:`${a.name || a.email || a.id}${a.role?` · ${a.role}`:''}`}));
  fillSelect('ekyteAssignee', assignees, draft.assignee_email || defaultAssigneeEmail(), 'Selecione');
  const routineOptions = routineTagRows().map(t=>({id:t.name,name:t.name, tagId:t.id||''}));
  $('ekyteRoutineTag').innerHTML = option('', 'Selecione', !draft.routine_tag_name) + routineOptions.map(t=>option(t.id,t.name,norm(t.name)===norm(draft.routine_tag_name),` data-id="${attr(t.tagId)}"`)).join('');
  const weekOptions = weekTagRows().map(t=>({id:t.name,name:t.name, tagId:t.id||''}));
  $('ekyteWeekTag').innerHTML = option('', 'Selecione', !draft.week_tag_name) + weekOptions.map(t=>option(t.id,t.name,norm(t.name)===norm(draft.week_tag_name),` data-id="${attr(t.tagId)}"`)).join('');
  $('ekyteDue').value = draft.due_date || localIsoPlus(2);
  $('ekyteMeetingDate').value = draft.meeting_date || meetingDateForClient(entry.item, draft);
  $('ekyteMessage').textContent = '';
  $('ekyteMessage').className = 'modal-msg';
  updateEkyteCreateState();
}
function currentEkytePayload() {
  const workspaceId = resolveSelectValue('ekyteWorkspace', 'ekyteWorkspaceOther');
  const projectId = resolveSelectValue('ekyteProject', 'ekyteProjectOther');
  const taskTypeId = resolveSelectValue('ekyteTaskType', 'ekyteTaskTypeOther');
  const assigneeEmail = resolveSelectValue('ekyteAssignee', 'ekyteAssigneeOther');
  return {
    item_id: pendingEkyte?.item?.id || '',
    workspace_id: workspaceId,
    workspace_label: resolveSelectLabel('ekyteWorkspace', 'ekyteWorkspaceOther'),
    project_id: projectId,
    project_name: resolveSelectLabel('ekyteProject', 'ekyteProjectOther'),
    task_type_id: taskTypeId,
    task_type_name: resolveSelectLabel('ekyteTaskType', 'ekyteTaskTypeOther'),
    assignee_email: assigneeEmail,
    assignee_name: resolveSelectLabel('ekyteAssignee', 'ekyteAssigneeOther').split(' · ')[0],
    due_date: $('ekyteDue').value,
    meeting_date: $('ekyteMeetingDate').value,
    routine_tag_name: $('ekyteRoutineTag').value,
    routine_tag_id: selectedData('ekyteRoutineTag','id'),
    week_tag_name: $('ekyteWeekTag').value,
    week_tag_id: selectedData('ekyteWeekTag','id'),
  };
}
function missingEkyteFields(payload) {
  const required = [
    ['workspace_id','workspace'],
    ['project_id','projeto'],
    ['task_type_id','tipo'],
    ['assignee_email','responsável'],
    ['due_date','prazo'],
    ['meeting_date','data da reunião'],
    ['routine_tag_name','tag de rotina'],
    ['week_tag_name','tag de semana'],
  ];
  return required.filter(([key])=>!payload[key]).map(([,label])=>label);
}
function updateEkyteCreateState() {
  if (!pendingEkyte) return;
  const missing = missingEkyteFields(currentEkytePayload());
  const disabled = missing.length > 0;
  $('ekyteCreateBtn').disabled = disabled;
  $('ekyteQueueBtn').disabled = disabled;
  if (disabled) {
    $('ekyteMessage').textContent = `Preencha: ${missing.join(', ')}`;
    $('ekyteMessage').className = 'modal-msg err';
  } else if ($('ekyteMessage').textContent.startsWith('Preencha:')) {
    $('ekyteMessage').textContent = '';
    $('ekyteMessage').className = 'modal-msg';
  }
}
function openEkyteModal(itemId) {
  const entry=allItems().find(({item})=>item.id===itemId);
  if (!entry) { showToast('Item não encontrado','err'); return; }
  const existing = clientPendingEkyteQueue.find(q=>q.item_id===itemId) || {};
  const draft = buildEkyteEntry(entry.category, entry.item, existing);
  pendingEkyte = entry;
  fillEkyteModal(entry, draft);
  $('ekyteModal').classList.remove('hidden');
}
function closeEkyteModal() {
  pendingEkyte = null;
  $('ekyteModal').classList.add('hidden');
}
async function queueEkyteFallback(category, item, overrides={}) {
  const existing=await readEkyteQueue();
  const entry=buildEkyteEntry(category,item,overrides);
  const queue=[...existing.filter(q=>q?.item_id!==item.id),entry];
  if (await tryWriteQueue(queue)) { syncPendingEkyteState(queue); item.ekaite_pending=true; showToast('Enfileirado em .todos/ekyte-pending.json'); render(); return; }
  syncPendingEkyteState(queue); item.ekaite_pending=true;
  try { downloadJson('ekyte-pending.json',queue); await copyText(JSON.stringify(queue,null,2)); showToast('Baixei ekyte-pending.json e copiei o JSON. Salve em .todos/.','err'); }
  catch { await copyText(JSON.stringify(queue,null,2)); showToast('JSON copiado — salve como .todos/ekyte-pending.json','err'); }
  render();
}
async function queueEkyte(itemId) {
  openEkyteModal(itemId);
}
async function saveEkyteQueueFromModal() {
  if (!pendingEkyte) return;
  const payload = currentEkytePayload();
  const missing = missingEkyteFields(payload);
  if (missing.length) { updateEkyteCreateState(); return; }
  try {
    const r=await postJson('/api/ekyte-queue',payload);
    syncPendingEkyteState([...clientPendingEkyteQueue.filter(q=>q.item_id!==payload.item_id),r.queued]);
    pendingEkyte.item.ekaite_pending=true;
    closeEkyteModal(); showToast('Task salva na fila Ekyte'); render();
  } catch(e) {
    await queueEkyteFallback(pendingEkyte.category,pendingEkyte.item,payload);
    closeEkyteModal();
  }
}
async function createEkyteFromModal() {
  if (!pendingEkyte) return;
  const payload = currentEkytePayload();
  const missing = missingEkyteFields(payload);
  if (missing.length) { updateEkyteCreateState(); return; }
  $('ekyteCreateBtn').disabled = true;
  $('ekyteMessage').textContent = 'Criando no Ekyte...';
  $('ekyteMessage').className = 'modal-msg';
  try {
    const r = await postJson('/api/ekyte-create', payload);
    pendingEkyte.item.ekaite_task_id = r.task_id;
    pendingEkyte.item.ekyte_task_id = r.task_id;
    pendingEkyte.item.ekaite_task_url = `https://app.ekyte.com/#/tasks/list/${r.task_id}/edit`;
    syncPendingEkyteState(clientPendingEkyteQueue.filter(q=>q.item_id!==payload.item_id));
    closeEkyteModal(); showToast(`Task criada no Ekyte #${r.task_id}`); render();
  } catch(e) {
    $('ekyteMessage').textContent = e.message || 'Falha ao criar no Ekyte';
    $('ekyteMessage').className = 'modal-msg err';
    updateEkyteCreateState();
  }
}
function normalizedPendingClient(entry) {
  const found = allItems().find(({item})=>item.id===entry.item_id);
  return found ? buildEkyteEntry(found.category, found.item, entry) : entry;
}
function renderEkyteFlushList(results=null) {
  const rowsToRender = results ? results.map(r=>({entry:r.entry, ok:r.ok, errors:r.errors||[]})) : clientPendingEkyteQueue.map(entry=>({entry:normalizedPendingClient(entry), ok:null, errors:[]}));
  $('ekyteFlushSummary').textContent = `${flushSelectedIds.size}/${clientPendingEkyteQueue.length} selecionadas`;
  if (!rowsToRender.length) { $('ekyteFlushList').innerHTML = '<div class="empty-state">Fila vazia.</div>'; return; }
  $('ekyteFlushList').innerHTML = rowsToRender.map(row => {
    const e = row.entry || {};
    const checked = flushSelectedIds.has(e.item_id);
    const cls = row.ok===true?' ok':row.ok===false?' err':'';
    const errors = row.errors?.length ? `<div class="queue-errors">${row.errors.map(esc).join('<br>')}</div>` : '';
    return `<div class="queue-row${cls}">
      <input class="queue-check" type="checkbox" data-flush-item="${attr(e.item_id)}" ${checked?'checked':''}>
      <div>
        <div class="queue-title">${esc(e.title||e.item_id)}</div>
        <div class="queue-meta">
          <span>${esc(e.project_name||e.project_id||'sem projeto')}</span>
          <span>·</span><span>${esc(e.assignee_name||e.assignee_email||'sem responsável')}</span>
          <span>·</span><span>${esc(e.due_date||'sem prazo')}</span>
          <span>·</span><span>${esc(e.routine_tag_name||'sem rotina')}</span>
          <span>·</span><span>${esc(e.week_tag_name||'sem semana')}</span>
          <span>·</span><button class="queue-edit-btn" type="button" data-edit-ekyte="${attr(e.item_id)}">Editar</button>
        </div>
        ${errors}
      </div>
    </div>`;
  }).join('');
}
function openEkyteFlushModal() {
  flushSelectedIds = new Set(clientPendingEkyteQueue.map(i=>i.item_id).filter(Boolean));
  flushValidationRows = null;
  $('ekyteFlushSelectAll').checked = true;
  $('ekyteFlushCreateBtn').disabled = true;
  $('ekyteFlushMessage').textContent = '';
  $('ekyteFlushMessage').className = 'modal-msg';
  renderEkyteFlushList();
  $('ekyteFlushModal').classList.remove('hidden');
}
function closeEkyteFlushModal() {
  $('ekyteFlushModal').classList.add('hidden');
}
async function validateEkyteFlush() {
  if (!flushSelectedIds.size) { $('ekyteFlushMessage').textContent='Selecione pelo menos uma task.'; $('ekyteFlushMessage').className='modal-msg err'; return; }
  $('ekyteFlushMessage').textContent = 'Validando fila...';
  $('ekyteFlushMessage').className = 'modal-msg';
  $('ekyteFlushCreateBtn').disabled = true;
  try {
    const r = await postJson('/api/ekyte-flush',{dry_run:true,item_ids:[...flushSelectedIds]});
    flushValidationRows = r.results || [];
    renderEkyteFlushList(flushValidationRows);
    if (r.valid) {
      $('ekyteFlushCreateBtn').disabled = false;
      $('ekyteFlushMessage').textContent = `${r.count} task(s) válidas para criação.`;
      $('ekyteFlushMessage').className = 'modal-msg ok';
    } else {
      $('ekyteFlushMessage').textContent = 'A fila tem pendências. Corrija os campos antes de criar.';
      $('ekyteFlushMessage').className = 'modal-msg err';
    }
  } catch(e) {
    $('ekyteFlushMessage').textContent = e.message || 'Falha ao validar fila.';
    $('ekyteFlushMessage').className = 'modal-msg err';
  }
}
async function createEkyteFlush() {
  if ($('ekyteFlushCreateBtn').disabled) return;
  $('ekyteFlushMessage').textContent = 'Criando tasks no Ekyte...';
  $('ekyteFlushMessage').className = 'modal-msg';
  try {
    const r = await postJson('/api/ekyte-flush',{dry_run:false,item_ids:[...flushSelectedIds]});
    syncPendingEkyteState(clientPendingEkyteQueue.filter(q=>!flushSelectedIds.has(q.item_id)));
    closeEkyteFlushModal(); showToast(`${r.successes?.length||0} task(s) criadas no Ekyte`); render();
  } catch(e) {
    $('ekyteFlushMessage').textContent = e.message || 'Falha ao criar fila.';
    $('ekyteFlushMessage').className = 'modal-msg err';
  }
}
async function copyFlushCmd() { await copyText('/todos-promote-ekaite'); showToast('Cole no Claude Code para criar as tasks','info'); }

document.addEventListener('click', e => {
  const toggle=e.target.closest('[data-toggle]');
  if (toggle) { const id=toggle.getAttribute('data-toggle'); const en=allItems().find(({item})=>item.id===id); if(en) toggleDone(en); return; }
  const scope=e.target.closest('[data-scope]');
  if (scope) {
    const s=scope.getAttribute('data-scope');
    filters.scope = (filters.scope===s && s!=='all') ? 'all' : s;
    render(); return;
  }
  const cat=e.target.closest('[data-category]');
  if (cat) { filters.category=cat.getAttribute('data-category'); render(); return; }
  const hide=e.target.closest('[data-hide-done]');
  if (hide) { const id=hide.getAttribute('data-hide-done'); hideDoneState[id]=!hideDoneState[id]; localStorage.setItem(`todos-hide-done:${DATA.meta.currentSprint}`,JSON.stringify(hideDoneState)); renderCategories(); return; }
  const collapse=e.target.closest('[data-collapse]');
  if (collapse) { const id=collapse.getAttribute('data-collapse'); collapsedState[id]=!collapsedState[id]; localStorage.setItem(`todos-collapsed:${DATA.meta.currentSprint}`,JSON.stringify(collapsedState)); renderCategories(); return; }
  const ekyte=e.target.closest('[data-ekyte]');
  if (ekyte) { queueEkyte(ekyte.getAttribute('data-ekyte')); return; }
  const editEkyte=e.target.closest('[data-edit-ekyte]');
  if (editEkyte) { closeEkyteFlushModal(); openEkyteModal(editEkyte.getAttribute('data-edit-ekyte')); return; }
  const flushItem=e.target.closest('[data-flush-item]');
  if (flushItem) {
    const id=flushItem.getAttribute('data-flush-item');
    if (flushItem.checked) flushSelectedIds.add(id); else flushSelectedIds.delete(id);
    $('ekyteFlushSelectAll').checked = flushSelectedIds.size === clientPendingEkyteQueue.length;
    $('ekyteFlushCreateBtn').disabled = true;
    flushValidationRows = null;
    renderEkyteFlushList();
    return;
  }
  if (e.target.id==='flushEkyteBtn') { openEkyteFlushModal(); return; }
  if (e.target.id==='ekyteCancelBtn' || e.target.id==='ekyteModal') { closeEkyteModal(); return; }
  if (e.target.id==='ekyteQueueBtn') { saveEkyteQueueFromModal(); return; }
  if (e.target.id==='ekyteCreateBtn') { createEkyteFromModal(); return; }
  if (e.target.id==='ekyteFlushCancelBtn' || e.target.id==='ekyteFlushModal') { closeEkyteFlushModal(); return; }
  if (e.target.id==='ekyteFlushValidateBtn') { validateEkyteFlush(); return; }
  if (e.target.id==='ekyteFlushCreateBtn') { createEkyteFlush(); return; }
  if (e.target.id==='completionCancelBtn') { cancelCompletion(); return; }
  if (e.target.id==='completionSkipBtn') { finishCompletion(false); return; }
  if (e.target.id==='completionSaveBtn') { finishCompletion(true); return; }
  if (e.target.id==='completionModal') { cancelCompletion(); return; }
  if (e.target.dataset.followDone) {
    const fid = e.target.dataset.followDone;
    const entry = followList.find(f => f.item_id === fid);
    if (entry) openFollowDismiss(entry);
    return;
  }
  if (e.target.id==='followDismissCancelBtn') { cancelFollowDismiss(); return; }
  if (e.target.id==='followDismissSkipBtn') { finishFollowDismiss(false); return; }
  if (e.target.id==='followDismissSaveBtn') { finishFollowDismiss(true); return; }
  if (e.target.id==='followDismissModal') { cancelFollowDismiss(); return; }
  if (e.target.id==='retryForceBtn') {
    const t=SYSTEM_STATE.refresh_trigger||{};
    if(t.from) $('refreshFrom').value=t.from;
    if(t.to) $('refreshTo').value=t.to;
    $('refreshForce').checked=true; $('refreshPanel').classList.add('visible'); createTrigger(true);
  }
});
$('searchInput').addEventListener('input', e => { filters.query=e.target.value.trim(); renderCategories(); renderHistoryView(); renderFollowView(); });
document.addEventListener('keydown', e => {
  if(e.key!=='Escape') return;
  if(!$('followDismissModal').classList.contains('hidden')) cancelFollowDismiss();
  else if(!$('completionModal').classList.contains('hidden')) cancelCompletion();
  else if(!$('ekyteModal').classList.contains('hidden')) closeEkyteModal();
  else if(!$('ekyteFlushModal').classList.contains('hidden')) closeEkyteFlushModal();
});
$('clearFiltersBtn').addEventListener('click', () => { filters.scope='all'; filters.category='all'; filters.query=''; $('searchInput').value=''; render(); });
$('manualToggleBtn').addEventListener('click', () => $('manualPanel').classList.toggle('visible'));
$('createManualBtn').addEventListener('click', createManualTask);
$('refreshToggleBtn').addEventListener('click', () => $('refreshPanel').classList.toggle('visible'));
$('refreshPreset').addEventListener('change', setPresetDates);
$('createTriggerBtn').addEventListener('click', () => createTrigger(false));
$('ekyteWorkspace').addEventListener('change', () => refreshEkyteProjectAndType());
['ekyteWorkspace','ekyteProject','ekyteTaskType','ekyteAssignee'].forEach(id => $(id).addEventListener('change', toggleEkyteOtherFields));
['ekyteProject','ekyteTaskType','ekyteAssignee','ekyteDue','ekyteMeetingDate','ekyteRoutineTag','ekyteWeekTag'].forEach(id => $(id).addEventListener('change', updateEkyteCreateState));
$('ekyteMeetingDate').addEventListener('change', () => {
  if (!$('ekyteWeekTag').value) $('ekyteWeekTag').value = weekTagForClient($('ekyteMeetingDate').value);
  updateEkyteCreateState();
});
$('ekyteFlushSelectAll').addEventListener('change', e => {
  flushSelectedIds = e.target.checked ? new Set(clientPendingEkyteQueue.map(i=>i.item_id).filter(Boolean)) : new Set();
  $('ekyteFlushCreateBtn').disabled = true;
  flushValidationRows = null;
  renderEkyteFlushList();
});
populateManualCategories();
setPresetDates();
render();
checkServer();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
