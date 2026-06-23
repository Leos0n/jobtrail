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
    rng = urllib.parse.quote(f"'{tab}'", safe="")
    url = f"{API}/{sid}/values/{rng}?majorDimension=ROWS&valueRenderOption=FORMATTED_VALUE"
    return _get(url, token).get("values", [])


_HYPERLINK_RE = re.compile(r'=HYPERLINK\(\s*"([^"]+)"', re.I)


def _cell_link(cell: dict):
    """Extract a URL a cell points to, however the link was added in Sheets.

    The plain ``values`` endpoint only returns a cell's display text (e.g.
    "Apply Here"), dropping the underlying link. Reading grid data lets us
    recover it from any of the three ways a Sheet stores a link: a cell-level
    hyperlink, a ``=HYPERLINK()`` formula, or a rich-text run link.
    """
    if cell.get("hyperlink"):
        return cell["hyperlink"]
    formula = (cell.get("userEnteredValue") or {}).get("formulaValue")
    if formula:
        m = _HYPERLINK_RE.search(formula)
        if m:
            return m.group(1)
    for run in cell.get("textFormatRuns") or []:
        uri = (((run.get("format") or {}).get("link")) or {}).get("uri")
        if uri:
            return uri
    return None


def read_tab_with_links(sid: str, tab: str, token: str):
    """Like :func:`read_tab`, but also return a parallel grid of cell links.

    Returns ``(values, links)`` where ``links[r][c]`` is the URL of that cell
    (or ``None``). Falls back to plain values (all links ``None``) if the grid
    read isn't available, so syncing never breaks on it.
    """
    rng = urllib.parse.quote(f"'{tab}'", safe="")
    fields = urllib.parse.quote(
        "sheets(data(rowData(values("
        "formattedValue,hyperlink,userEnteredValue/formulaValue,"
        "textFormatRuns(format/link/uri)))))"
    )
    url = f"{API}/{sid}?ranges={rng}&includeGridData=true&fields={fields}"
    try:
        data = _get(url, token)
        sheets = data.get("sheets") or []
        grid = (sheets[0].get("data") or [{}])[0].get("rowData") or []
    except Exception:
        vals = read_tab(sid, tab, token)
        return vals, [[None] * len(r) for r in vals]

    values, links = [], []
    for row in grid:
        cells = row.get("values") or []
        values.append([c.get("formattedValue", "") for c in cells])
        links.append([_cell_link(c) for c in cells])
    return values, links
