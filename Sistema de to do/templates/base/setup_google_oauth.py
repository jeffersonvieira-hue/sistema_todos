#!/usr/bin/env python3
"""Authorize Google Calendar and Drive for the automatic todos sync."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict


CLIENT_PATH = Path.home() / ".claude/gdrive/credentials.json"
TOKEN_PATH = Path.home() / ".config/todos-auto-sync/google-token.json"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def load_client() -> Dict[str, Any]:
    payload = json.loads(CLIENT_PATH.read_text(encoding="utf-8"))
    client = payload.get("installed") or payload.get("web") or {}
    if not client.get("client_id") or not client.get("client_secret"):
        raise RuntimeError(f"Credenciais OAuth incompletas em {CLIENT_PATH}")
    return client


def post_form(url: str, payload: Dict[str, str]) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    client = load_client()
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    result: Dict[str, str] = {}
    completed = threading.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if query.get("state", [""])[0] != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Estado OAuth invalido.")
                return
            if query.get("error"):
                result["error"] = query["error"][0]
            else:
                result["code"] = query.get("code", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<html><body style='font-family:system-ui;padding:40px'>"
                "<h2>Autorizacao concluida</h2>"
                "<p>Voce pode fechar esta aba e voltar ao Codex.</p>"
                "</body></html>".encode("utf-8")
            )
            completed.set()

        def log_message(self, *_args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
    port = server.server_address[1]
    redirect_uri = f"http://localhost:{port}"
    auth_params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(auth_params)

    print("Abrindo autorizacao do Google no navegador...")
    print("Aguardando permissao para Google Calendar e Google Drive.")
    webbrowser.open(url)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if not completed.wait(timeout=300):
        server.shutdown()
        raise RuntimeError("Tempo de autorizacao expirou.")
    server.shutdown()

    if result.get("error"):
        raise RuntimeError(f"Google recusou a autorizacao: {result['error']}")
    if not result.get("code"):
        raise RuntimeError("Google nao retornou o codigo de autorizacao.")

    token = post_form(
        TOKEN_URL,
        {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "code": result["code"],
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if not token.get("refresh_token"):
        raise RuntimeError(
            "Google nao retornou refresh_token. Revogue o acesso antigo e tente novamente."
        )

    token["created_at"] = int(time.time())
    token["expiry_date"] = int(
        (time.time() + int(token.get("expires_in", 3600))) * 1000
    )
    token["scopes_requested"] = SCOPES
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(
        json.dumps(token, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    TOKEN_PATH.chmod(0o600)
    print(f"OK: token salvo em {TOKEN_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
