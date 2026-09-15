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
| 2 | Multi-source search core and search API | 🚧 In progress |
| 3 | SQLite scan and paper persistence | ⏳ Planned |
| 4 | BYOK paper analysis | ⏳ Planned |
| 5 | Local Web UI | ⏳ Planned |
| 6 | GitHub Pages presentation | ⏳ Planned |

The current `main` branch is the Phase 1 foundation. It does **not** yet provide live search, a running API, persistence, AI analysis, or a Web UI. Phase 2 work takes place on a separate feature branch until reviewed.

## Planned V1

- Search OpenAlex, arXiv, and Crossref through one service, with normalization, deduplication, ranking, and honest provider status.
- Keep scan and paper identities in SQLite so later analysis can use already found papers.
- Offer BYOK analysis without committing or permanently storing an LLM key.
- Provide a local FastAPI interface and, separately, a static Pages presentation.

These are roadmap items, not claims about the current release.

## Architecture

The Phase 2 target is:

```text
Query → SearchService → OpenAlex / arXiv / Crossref
      → normalize → deduplicate → rank → SearchResult
                          ↑
                    FastAPI search route
```

Future persistence and analysis will consume this result; neither the API nor a future UI will implement its own provider search logic.

## Project Structure

```text
src/litwatch/
  api/        FastAPI boundary (reserved in Phase 1)
  core/       shared domain models (reserved)
  providers/  academic-source adapters (reserved)
  search/     unified search pipeline (reserved)
  storage/    future SQLite persistence (reserved)
  analysis/   future BYOK analysis (reserved)
  web/        future local UI (reserved)
tests/        package foundation tests
.github/workflows/ci.yml  Linux/Windows pytest and independent Ruff checks
```

## Quick Start

Use Python 3.12 or newer and [uv](https://docs.astral.sh/uv/). Today this only installs and validates the foundation:

```powershell
git clone https://github.com/HQY-qianqiuwu/litwatch.git
cd litwatch
uv sync --extra dev
uv run python -c "import litwatch; print(litwatch.__file__)"
uv run pytest
uv run ruff check .
```

There is no server or search command on `main` yet. The Phase 2 branch will add `GET /health`, `GET /api/v1/providers`, and `POST /api/v1/literature/search` before documenting live usage.

## Development Workflow

Keep features on focused branches, add tests for new behavior, and run `uv run pytest` and `uv run ruff check .` before commits. CI runs the Python test job on both Ubuntu and Windows; Ruff is its own job. See [Migration Matrix](docs/MIGRATION_MATRIX.md) for what may be selectively referenced from the older repository.

## Security

Only `.env.example` belongs in Git. Never commit `.env`, API keys, credentials, user data, generated SQLite files, or a virtual environment. Phase 4 BYOK keys are planned to be request-scoped and excluded from persistence, logs, and responses. Phase 1 requires no secret.

## Roadmap

Phase 2 establishes the search core and API without a database or LLM. Phase 3 adds stable SQLite identities; Phase 4 adds analysis; Phase 5 adds local visualization; Phase 6 adds optional static Pages presentation. Scheduler, Email, Radar, Zotero, Dify, Prompt Library, Windows Task, and Docker are outside this project's V1 scope.

## License / Attribution

LitWatch is licensed under [MIT](LICENSE). The new repository has independent Git history. [NOTICE.md](NOTICE.md) records the older MIT-licensed reference and the attribution rule for any later substantial adaptation; this foundation contains no copied old implementation.
