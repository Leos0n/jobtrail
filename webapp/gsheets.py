"""Google Sheets REST API reads — stdlib urllib only (no client library).

Read-only: list a spreadsheet's tabs and read a tab's values. Auth is a bearer
access token obtained via webapp.gauth.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

API = "https://sheets.googleapis.com/v4/spreadsheets"


def spreadsheet_id(url_or_id: str) -> str:
    """Extract the spreadsheet id from a Sheets URL or accept a bare id."""
    s = (url_or_id or "").strip()
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", s):
        return s
    raise ValueError(f"could not parse a spreadsheet id from: {url_or_id!r}")


def _get(url: str, token: str):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            pass
        raise RuntimeError(f"Sheets API HTTP {e.code}: {detail or e.reason}") from e


def list_tabs(sid: str, token: str) -> list[str]:
    fields = urllib.parse.quote("sheets(properties(title,sheetId,gridProperties))")
    data = _get(f"{API}/{sid}?fields={fields}", token)
    return [s["properties"]["title"] for s in data.get("sheets", [])]


def read_tab(sid: str, tab: str, token: str) -> list[list]:
    """Return a tab's values as a list of rows (each row a list of cells)."""
    rng = urllib.parse.quote(f"'{tab}'")
    url = f"{API}/{sid}/values/{rng}?majorDimension=ROWS&valueRenderOption=FORMATTED_VALUE"
    return _get(url, token).get("values", [])
