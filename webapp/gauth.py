"""Google OAuth 2.0 for JobTrail — stdlib only, Authorization Code + PKCE.

Designed for the open-source / bring-your-own-credentials model:
  * The user supplies their OWN OAuth "Desktop app" client (credentials.json).
  * This repo ships NO Google secrets.
  * The flow runs entirely on the user's machine: consent in the browser, the
    redirect is caught on a 127.0.0.1 loopback port, and the resulting refresh
    token is stored locally (user-only permissions, git-ignored).
  * Scope is read-only Sheets. There is no shared server, so no two users'
    data can ever overlap.

No google-auth / google-api-python-client dependency — just urllib + http.server.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"


class AuthError(RuntimeError):
    """Raised when a stored Google authorization can no longer be used."""


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def pkce_pair():
    """Return (verifier, challenge) for PKCE S256."""
    verifier = _b64url(secrets.token_bytes(40))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def load_client(credentials_path):
    data = json.loads(Path(credentials_path).read_text(encoding="utf-8"))
    cfg = data.get("installed") or data.get("web")
    if not cfg or "client_id" not in cfg:
        raise ValueError(
            "credentials.json must be a Google 'Desktop app' OAuth client "
            "(an 'installed' section with client_id/client_secret)."
        )
    return cfg["client_id"], cfg.get("client_secret", "")


def build_auth_url(client_id, redirect_uri, challenge, state):
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "include_granted_scopes": "true",
    }
    return AUTH_URI + "?" + urllib.parse.urlencode(params)


class _CatchHandler(http.server.BaseHTTPRequestHandler):
    result = {}

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _CatchHandler.result = {k: v[0] for k, v in q.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        ok = "code" in _CatchHandler.result
        msg = "JobTrail is connected to Google Sheets." if ok else "Authorization was cancelled."
        self.wfile.write(
            (f"<!doctype html><meta charset=utf-8><body style='font-family:system-ui;"
             f"background:#faf6ec;color:#26211c;display:grid;place-items:center;height:100vh;margin:0'>"
             f"<div style='text-align:center'><h2 style='font-weight:600'>{msg}</h2>"
             f"<p style='color:#7a7166'>You can close this tab and return to JobTrail.</p></div>"
             ).encode("utf-8")
        )

    def log_message(self, *a):
        pass


def _post(url, data):
    body = urllib.parse.urlencode(data).encode("ascii")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _save_token(token_path, tok):
    p = Path(token_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(tok), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def run_connect(credentials_path, token_path):
    """Run the full interactive consent flow; persist and return the token."""
    client_id, client_secret = load_client(credentials_path)
    verifier, challenge = pkce_pair()
    state = _b64url(secrets.token_bytes(16))

    server = http.server.HTTPServer(("127.0.0.1", 0), _CatchHandler)
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}/"
    url = build_auth_url(client_id, redirect_uri, challenge, state)

    print("Opening your browser to authorize JobTrail (read-only Google Sheets).")
    print("If it doesn't open automatically, visit:\n  " + url + "\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    server.handle_request()  # blocks until the redirect arrives
    server.server_close()

    res = _CatchHandler.result
    if res.get("error"):
        raise RuntimeError("authorization failed: " + res["error"])
    if res.get("state") != state:
        raise RuntimeError("state mismatch (possible CSRF) — aborted")
    if not res.get("code"):
        raise RuntimeError("no authorization code received")

    tok = _post(TOKEN_URI, {
        "code": res["code"],
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    })
    if "refresh_token" not in tok:
        raise RuntimeError(
            "Google did not return a refresh token. Revoke prior access at "
            "https://myaccount.google.com/permissions and reconnect."
        )
    tok["_client_id"] = client_id
    tok["_client_secret"] = client_secret
    tok["_obtained"] = int(time.time())
    _save_token(token_path, tok)
    return tok


def access_token(token_path):
    """Return a valid access token, refreshing if needed."""
    tok = json.loads(Path(token_path).read_text(encoding="utf-8"))
    age = int(time.time()) - tok.get("_obtained", 0)
    if tok.get("access_token") and age < tok.get("expires_in", 3600) - 120:
        return tok["access_token"]
    try:
        fresh = _post(TOKEN_URI, {
            "client_id": tok["_client_id"],
            "client_secret": tok["_client_secret"],
            "refresh_token": tok["refresh_token"],
            "grant_type": "refresh_token",
        })
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", "")
        except Exception:
            pass
        # invalid_grant = the refresh token was revoked or expired (common for
        # OAuth clients left in "Testing" status, which Google caps at 7 days).
        raise AuthError(
            f"Google rejected the refresh token ({detail or exc.code}). Your "
            "authorization has likely expired or been revoked — reconnect by "
            "running `bin/jobtrail-google`."
        ) from exc
    if "access_token" not in fresh:
        raise AuthError(
            "Google did not return a new access token "
            f"({fresh.get('error', 'unknown error')}). Reconnect by running "
            "`bin/jobtrail-google`."
        )
    tok["access_token"] = fresh["access_token"]
    tok["expires_in"] = fresh.get("expires_in", 3600)
    tok["_obtained"] = int(time.time())
    if fresh.get("refresh_token"):
        tok["refresh_token"] = fresh["refresh_token"]
    _save_token(token_path, tok)
    return tok["access_token"]


def is_connected(token_path):
    return Path(token_path).is_file()
