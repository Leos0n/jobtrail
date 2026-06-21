"""Convert a fragment of job-description HTML into clean Markdown.

Indeed embeds the job description as an HTML string inside its JobPosting
JSON-LD. That HTML is small and predictable (paragraphs, line breaks, bullet
lists, bold/italic, the odd heading or link), so we can convert it with the
standard-library ``html.parser`` instead of pulling in a dependency.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# Tags whose contents we never want to emit.
_DROP_CONTENT = {"script", "style", "head", "title", "noscript"}
# Block-level tags that should be separated by a blank line.
_BLOCK = {"p", "div", "section", "article", "header", "footer", "table", "tr"}


class _MarkdownParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._drop_depth = 0
        self._bold = 0
        self._italic = 0
        self._href: str | None = None
        # Stack of ("ul", None) or ("ol", counter) describing nested lists.
        self._lists: list[list] = []

    # -- helpers ---------------------------------------------------------
    def _emit(self, text: str) -> None:
        self.out.append(text)

    def _newline(self, count: int = 1) -> None:
        self.out.append("\n" * count)

    @property
    def _indent(self) -> str:
        # Two spaces per nesting level beyond the first list.
        return "  " * max(0, len(self._lists) - 1)

    # -- tag handling ----------------------------------------------------
    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _DROP_CONTENT:
            self._drop_depth += 1
            return
        if self._drop_depth:
            return

        if tag in _BLOCK:
            self._newline(2)
        elif tag == "br":
            self._newline(1)
        elif tag in ("ul", "ol"):
            self._newline(1)
            self._lists.append([tag, 0])
        elif tag == "li":
            self._newline(1)
            if self._lists and self._lists[-1][0] == "ol":
                self._lists[-1][1] += 1
                marker = f"{self._lists[-1][1]}. "
            else:
                marker = "- "
            self._emit(self._indent + marker)
        elif tag in ("strong", "b"):
            self._bold += 1
            self._emit("**")
        elif tag in ("em", "i"):
            self._italic += 1
            self._emit("*")
        elif re.fullmatch(r"h[1-6]", tag):
            level = int(tag[1])
            self._newline(2)
            self._emit("#" * level + " ")
        elif tag == "a":
            href = dict(attrs).get("href")
            if href and not href.startswith("javascript:"):
                self._href = href
                self._emit("[")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROP_CONTENT:
            self._drop_depth = max(0, self._drop_depth - 1)
            return
        if self._drop_depth:
            return

        if tag in _BLOCK:
            self._newline(2)
        elif tag in ("ul", "ol"):
            if self._lists:
                self._lists.pop()
            self._newline(1)
        elif tag in ("strong", "b") and self._bold:
            self._bold -= 1
            self._emit("**")
        elif tag in ("em", "i") and self._italic:
            self._italic -= 1
            self._emit("*")
        elif re.fullmatch(r"h[1-6]", tag):
            self._newline(2)
        elif tag == "a" and self._href is not None:
            self._emit(f"]({self._href})")
            self._href = None

    def handle_data(self, data: str) -> None:
        if self._drop_depth:
            return
        # Collapse runs of inline whitespace but keep meaningful spaces.
        text = re.sub(r"[ \t\r\f\v]+", " ", data.replace("\n", " "))
        if text.strip() == "" and (not self.out or self.out[-1].endswith("\n")):
            return
        self._emit(text)


def _normalize(markdown: str) -> str:
    """Tidy whitespace: trim lines, collapse >2 blank lines, strip ends."""
    lines = [ln.rstrip() for ln in markdown.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_to_markdown(html: str) -> str:
    """Convert an HTML fragment to Markdown. Returns ``""`` for empty input."""
    if not html or not html.strip():
        return ""
    # If the input has no tags at all, treat it as plain text.
    if "<" not in html:
        return _normalize(html)
    parser = _MarkdownParser()
    parser.feed(html)
    parser.close()
    return _normalize("".join(parser.out))
