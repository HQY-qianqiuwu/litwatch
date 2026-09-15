# LitWatch

[![CI](https://github.com/HQY-qianqiuwu/litwatch/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/HQY-qianqiuwu/litwatch/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

LitWatch is a standalone Python project for finding relevant academic papers across multiple sources. Its guiding rule is simple: one search core finds papers; later analysis reads those papers without searching again.

## Why LitWatch

Literature discovery is scattered across services, and duplicate records make results harder to review. LitWatch is being built as a small, inspectable search pipeline with normalized metadata, deterministic ranking, and clear source-failure reporting. It starts fresh rather than carrying over the older project's automation and compatibility layers.

## Current Status

| Phase | Capability | Status |
| --- | --- | --- |
| 1 | Foundation: installable package, tests, CI | ✅ Complete |
| 2 | Multi-source search core and search API | ✅ Complete |
| 3 | SQLite scan and paper persistence | ✅ Complete |
| 4 | BYOK paper analysis | ⏳ Next |
| 5 | Local Web UI | ⏳ Planned |
| 6 | GitHub Pages presentation | ⏳ Planned |

The current `main` branch includes Phase 1 Foundation, Phase 2 Search Core, and Phase 3 Persistence. It provides live multi-source search with persistent scans and stable paper IDs, but not yet AI analysis or a Web UI. Phase 4 BYOK Analysis is next.

## Planned V1

- Search OpenAlex, arXiv, and Crossref through one service, with normalization, deduplication, ranking, and honest provider status.
- Keep scan and paper identities in SQLite so later analysis can use already found papers.
- Offer BYOK analysis without committing or permanently storing an LLM key.
- Provide a local FastAPI interface and, separately, a static Pages presentation.

The search core and persistence are complete; analysis and presentation remain roadmap items.

## Architecture

The current search path is:

```text
Query → SearchService → OpenAlex / arXiv / Crossref
      → normalize → deduplicate → rank → SearchResult
      → SQLite persistence → scan_id / stable paper_id
      → FastAPI search response
```

Future analysis will read persisted papers; neither the API nor a future UI will implement its own provider search logic.

## Project Structure

```text
src/litwatch/
  api/        FastAPI search boundary
  core/       shared search models and identities
  providers/  OpenAlex, arXiv, and Crossref adapters
  search/     unified search pipeline
  storage/    SQLite scans, paper identities, and aliases
  analysis/   future BYOK analysis (reserved)
  web/        future local UI (reserved)
tests/        foundation, search-core, and persistence tests
.github/workflows/ci.yml  Linux/Windows pytest and independent Ruff checks
```

## Quick Start

Use Python 3.12 or newer and [uv](https://docs.astral.sh/uv/) to install and validate the project:

```powershell
git clone https://github.com/HQY-qianqiuwu/litwatch.git
cd litwatch
uv sync --extra dev
uv run python -c "import litwatch; print(litwatch.__file__)"
uv run pytest
uv run ruff check .
```

The search API provides `GET /health`, `GET /api/v1/providers`, and `POST /api/v1/literature/search`. Search responses include persisted `scan_id` and `paper_id` values.

## Development Workflow

Keep features on focused branches, add tests for new behavior, and run `uv run pytest` and `uv run ruff check .` before commits. CI runs the Python test job on both Ubuntu and Windows; Ruff is its own job. See [Migration Matrix](docs/MIGRATION_MATRIX.md) for what may be selectively referenced from the older repository.

## Security

Only `.env.example` belongs in Git. Never commit `.env`, API keys, credentials, user data, generated SQLite files, or a virtual environment. Phase 4 BYOK keys are planned to be request-scoped and excluded from persistence, logs, and responses. Search and persistence require no secret.

## Roadmap

Phase 2 established the search core and API; Phase 3 added stable SQLite identities and persistent deduplication. Phase 4 next adds BYOK analysis; Phase 5 adds local visualization; Phase 6 adds optional static Pages presentation. Scheduler, Email, Radar, Zotero, Dify, Prompt Library, Windows Task, and Docker are outside this project's V1 scope.

## License / Attribution

LitWatch is licensed under [MIT](LICENSE). The new repository has independent Git history. [NOTICE.md](NOTICE.md) records the older MIT-licensed reference and the attribution rule for any later substantial adaptation; this foundation contains no copied old implementation.
