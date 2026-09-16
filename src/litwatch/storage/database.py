"""Short-lived SQLite connections and additive Phase 3 schema creation."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS search_scans (
                    scan_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider_results TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS papers (
                    paper_id TEXT PRIMARY KEY,
                    normalized_title TEXT NOT NULL,
                    doi TEXT,
                    arxiv_id TEXT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS papers_title_idx ON papers(normalized_title);
                CREATE TABLE IF NOT EXISTS scan_papers (
                    scan_id TEXT NOT NULL REFERENCES search_scans(scan_id),
                    paper_id TEXT NOT NULL REFERENCES papers(paper_id),
                    position INTEGER NOT NULL,
                    score REAL NOT NULL,
                    PRIMARY KEY (scan_id, paper_id)
                );
                CREATE TABLE IF NOT EXISTS paper_aliases (
                    kind TEXT NOT NULL,
                    value TEXT NOT NULL,
                    paper_id TEXT NOT NULL REFERENCES papers(paper_id),
                    PRIMARY KEY (kind, value)
                );
                CREATE INDEX IF NOT EXISTS paper_aliases_paper_idx
                    ON paper_aliases(paper_id);
                CREATE TABLE IF NOT EXISTS paper_redirects (
                    old_paper_id TEXT PRIMARY KEY,
                    paper_id TEXT NOT NULL REFERENCES papers(paper_id)
                );
                CREATE INDEX IF NOT EXISTS paper_redirects_paper_idx
                    ON paper_redirects(paper_id);
                CREATE TABLE IF NOT EXISTS analyses (
                    analysis_id TEXT PRIMARY KEY,
                    paper_id TEXT NOT NULL REFERENCES papers(paper_id),
                    analysis_mode TEXT NOT NULL,
                    model TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS analyses_paper_idx ON analyses(paper_id);
                """
            )
