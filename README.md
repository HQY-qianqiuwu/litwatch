# LitWatch

Multi-source academic literature search and AI-assisted paper analysis.

API finds papers. AI reads papers.

## What is LitWatch

LitWatch is a clean, standalone Python project for searching real academic metadata,
keeping stable paper identities, and analyzing papers with a user-supplied LLM key.
This first commit is the importable project foundation only; search, storage, analysis,
and the user interface arrive in later, separately verified phases.

## Features

Planned V1 features are OpenAlex, arXiv, and Crossref search; normalization, deduplication,
and relevance ranking; SQLite scan and paper persistence; ephemeral BYOK paper analysis;
and a local HTML/CSS/JavaScript interface. None of those features is implemented in Phase 1.

## Architecture

The package reserves focused boundaries for `api`, `core`, `providers`, `search`,
`storage`, `analysis`, and `web`. The planned rule is one literature search core:
API finds papers; AI reads already saved papers.

## Quick Start

Use Python 3.12 or newer and [uv](https://docs.astral.sh/uv/):

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check .
```

There is no server or search command in this foundation commit yet.

## Search API

Phase 2 will introduce `GET /health`, `GET /api/v1/providers`, and
`POST /api/v1/literature/search`. This section will be expanded with real
request and response examples once those routes exist.

## BYOK AI Analysis

Phase 4 will add analysis of papers already saved by a Search. LLM keys will be
supplied per request and kept out of SQLite, logs, responses, and Git.
No LLM key is needed for this foundation.

## Web UI

Phase 5 will add a local FastAPI-rendered interface using HTML, CSS, and
vanilla JavaScript. There is no React, Vue, or frontend build dependency.

## GitHub Pages

Phase 6 will publish a separate static interface at
`https://HQY-qianqiuwu.github.io/litwatch/`. Pages will not host FastAPI;
live search will require a separately configured public LitWatch API.

## Security

Commit only `.env.example`, never `.env`, API keys, SMTP credentials,
user data, or generated SQLite files. V1 BYOK will not permanently store
the user's LLM key.

## Development

Run `uv run pytest` and `uv run ruff check .` before each development commit.
CI will run Python checks on Linux and Windows. This foundation does not include
Scheduler, Email, Dify, Radar, Zotero, PowerShell lifecycle, or Docker.

## License / Attribution

This new project is licensed under MIT. See [LICENSE](LICENSE) and
[NOTICE.md](NOTICE.md) for the Stage 2 reference source and future attribution rules.
