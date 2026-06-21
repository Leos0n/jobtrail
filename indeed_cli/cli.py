"""Command-line interface for Indeed-CLI.

Examples
--------
    # One job to stdout
    indeed-cli "https://www.indeed.com/viewjob?jk=abcd1234" --stdout

    # Several jobs, written as Markdown files into ./output
    indeed-cli URL1 URL2 URL3

    # A batch from a file (one URL per line, '#' comments allowed)
    indeed-cli --file urls.txt -o jobs/

    # Parse a page you already saved (no network needed)
    indeed-cli --html saved.html --url "https://www.indeed.com/viewjob?jk=abcd1234"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from .fetch import FetchError
from .parse import Job
from .render import filename_for, render_markdown
from .sources import fetch_and_parse, parse_local


def _read_url_file(path: Path) -> list[str]:
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def _gather_urls(args) -> list[str]:
    urls = list(args.urls)
    if args.file:
        urls.extend(_read_url_file(Path(args.file)))
    # De-duplicate while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered


def _job_to_dict(job: Job) -> dict:
    d = asdict(job)
    # The raw HTML description is noisy in JSON output; keep the markdown.
    d.pop("description_html", None)
    return d


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="indeed-cli",
        description="Turn Indeed job links into clean Markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("urls", nargs="*", help="One or more Indeed job URLs.")
    p.add_argument("-f", "--file", help="File with one job URL per line.")
    p.add_argument(
        "-o",
        "--output-dir",
        default="output",
        help="Directory for generated .md files (default: ./output).",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        help="Print Markdown to stdout instead of writing files.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON array of structured job records to stdout.",
    )
    p.add_argument(
        "--html",
        help="Parse this local HTML file instead of fetching (needs --url).",
    )
    p.add_argument(
        "--url",
        help="Original URL to associate with --html input.",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait between requests in a batch (default: 2.0).",
    )
    p.add_argument(
        "--timeout", type=float, default=30.0, help="Per-request timeout seconds."
    )
    p.add_argument(
        "--retries", type=int, default=3, help="Retries per URL on blocking/errors."
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    jobs: list[Job] = []
    errors: list[tuple[str, str]] = []

    # ---- Local-HTML mode -------------------------------------------------
    if args.html:
        url = args.url or args.html
        try:
            html = Path(args.html).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"error: cannot read {args.html}: {e}", file=sys.stderr)
            return 2
        jobs.append(parse_local(html, url))
    else:
        # ---- Network mode ------------------------------------------------
        urls = _gather_urls(args)
        if not urls:
            build_parser().print_help(sys.stderr)
            return 2
        total = len(urls)
        for i, url in enumerate(urls, 1):
            if total > 1:
                print(f"[{i}/{total}] fetching {url}", file=sys.stderr)
            try:
                jobs.append(
                    fetch_and_parse(url, timeout=args.timeout, retries=args.retries)
                )
            except FetchError as e:
                errors.append((url, str(e)))
                print(f"  ! {e}", file=sys.stderr)
            if i < total and args.delay > 0:
                time.sleep(args.delay)

    # ---- Output ----------------------------------------------------------
    if args.json:
        print(json.dumps([_job_to_dict(j) for j in jobs], indent=2, ensure_ascii=False))
    elif args.stdout:
        print(("\n\n" + "=" * 72 + "\n\n").join(render_markdown(j) for j in jobs))
    else:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for job in jobs:
            path = out_dir / filename_for(job)
            path.write_text(render_markdown(job), encoding="utf-8")
            print(f"wrote {path}", file=sys.stderr)

    # ---- Summary ---------------------------------------------------------
    if errors:
        print(
            f"\n{len(errors)} of {len(jobs) + len(errors)} URL(s) failed.",
            file=sys.stderr,
        )
        return 1 if jobs else 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
