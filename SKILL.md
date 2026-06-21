---
name: indeed-cli
description: "Turn an Indeed job link into clean Markdown — role, requirements, pay, location. Single or batch. Zero dependencies (Python stdlib)."
author: "Indeed-CLI"
license: "MIT"
argument-hint: "<indeed-url> [more-urls] | --file urls.txt | --html saved.html --url <url>"
allowed-tools: "Read Bash"
---

# Indeed-CLI

Extract structured details from Indeed job postings as Markdown.

## Prerequisites

No install needed beyond Python 3.9+. Run the launcher from the `Indeed-CLI/`
directory:

```bash
./bin/indeed-cli --help
```

## Common commands

```bash
# One job to the terminal
./bin/indeed-cli "https://www.indeed.com/viewjob?jk=JOBKEY" --stdout

# Batch -> Markdown files in ./output
./bin/indeed-cli URL1 URL2 URL3
./bin/indeed-cli --file examples/urls.txt -o jobs/

# Structured JSON
./bin/indeed-cli "https://www.indeed.com/viewjob?jk=JOBKEY" --json

# Offline: parse a saved page (use when Indeed returns HTTP 403)
./bin/indeed-cli --html saved.html --url "https://www.indeed.com/viewjob?jk=JOBKEY" --stdout
```

## How it works

Reads the schema.org `JobPosting` JSON-LD embedded in each Indeed page (primary
source), with `_initialData` and `<title>` fallbacks. Converts the HTML
description to Markdown with the standard-library parser. No third-party
packages.

## When a live fetch is blocked

Indeed challenges automated requests; a direct fetch may return HTTP 403. The
fallback is identical output from a browser-saved page via `--html`. Keep volume
modest and respect Indeed's Terms of Service.

## Verify

```bash
python3 -m unittest discover -s tests -v   # fully offline
```
