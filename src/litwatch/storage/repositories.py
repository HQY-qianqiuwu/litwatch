"""Persist search snapshots and paper records without searching providers."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from litwatch.core import Paper, SearchResult
from litwatch.core.identity import normalized_title
from litwatch.storage.database import Database
from litwatch.storage.identity import enrich, find_matches, identity_aliases, prepare_paper
from litwatch.storage.reconciliation import reconcile


def _linked_papers(connection, scan_id: str) -> list[Paper]:
    linked = connection.execute(
        """SELECT papers.paper_id, papers.payload, scan_papers.score
           FROM scan_papers JOIN papers USING (paper_id)
           WHERE scan_papers.scan_id = ? ORDER BY scan_papers.position""",
        (scan_id,),
    ).fetchall()
    papers = []
    for item in linked:
        paper = Paper.model_validate_json(item["payload"])
        paper.paper_id = item["paper_id"]
        paper.score = item["score"]
        papers.append(paper)
    return papers


class SearchRepository:
    def __init__(self, path: str | Path) -> None:
        self.database = Database(path)

    def save(self, result: SearchResult) -> SearchResult:
        saved = result.model_copy(deep=True)
        saved.scan_id = f"S-{uuid4().hex}"
        now = datetime.now(UTC).isoformat()
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO search_scans VALUES (?, ?, ?, ?, ?)",
                (
                    saved.scan_id,
                    saved.topic,
                    saved.status.value,
                    json.dumps([item.model_dump(mode="json") for item in saved.provider_results]),
                    now,
                ),
            )
            for position, paper in enumerate(saved.papers):
                incoming = prepare_paper(paper)
                matches = find_matches(connection, incoming)
                if not matches:
                    incoming.paper_id = f"P-{uuid4().hex}"
                    stored = incoming
                else:
                    stored = enrich(reconcile(connection, matches), incoming)

                stored.aliases = [
                    alias
                    for alias in stored.aliases
                    if (
                        owner := connection.execute(
                            "SELECT paper_id FROM paper_aliases WHERE kind = 'provider' AND value = ?",
                            (f"{alias.provider.casefold()}:{alias.provider_id.casefold()}",),
                        ).fetchone()
                    ) is None or owner["paper_id"] == stored.paper_id
                ]
                if stored.arxiv_id:
                    arxiv_owner = connection.execute(
                        "SELECT paper_id FROM paper_aliases WHERE kind = 'arxiv' AND value = ?",
                        (stored.arxiv_id,),
                    ).fetchone()
                    if arxiv_owner is not None and arxiv_owner["paper_id"] != stored.paper_id:
                        stored.arxiv_id = None
                if not matches:
                    connection.execute(
                        "INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            stored.paper_id,
                            normalized_title(stored.title),
                            stored.doi,
                            stored.arxiv_id,
                            stored.model_dump_json(exclude={"paper_id"}),
                            now,
                            now,
                        ),
                    )
                else:
                    connection.execute(
                        """UPDATE papers SET normalized_title = ?, doi = ?, arxiv_id = ?,
                           payload = ?, updated_at = ? WHERE paper_id = ?""",
                        (
                            normalized_title(stored.title),
                            stored.doi,
                            stored.arxiv_id,
                            stored.model_dump_json(exclude={"paper_id"}),
                            now,
                            stored.paper_id,
                        ),
                    )
                for kind, value in identity_aliases(stored):
                    owner = connection.execute(
                        "SELECT paper_id FROM paper_aliases WHERE kind = ? AND value = ?",
                        (kind, value),
                    ).fetchone()
                    if owner is None:
                        connection.execute(
                            "INSERT INTO paper_aliases VALUES (?, ?, ?)",
                            (kind, value, stored.paper_id),
                        )
                    elif owner["paper_id"] != stored.paper_id:
                        raise ValueError(f"identity alias conflict: {kind}:{value}")
                linked = connection.execute(
                    "SELECT position, score FROM scan_papers WHERE scan_id = ? AND paper_id = ?",
                    (saved.scan_id, stored.paper_id),
                ).fetchone()
                if linked is None:
                    connection.execute(
                        "INSERT INTO scan_papers VALUES (?, ?, ?, ?)",
                        (saved.scan_id, stored.paper_id, position, incoming.score),
                    )
                else:
                    connection.execute(
                        """UPDATE scan_papers SET position = ?, score = ?
                           WHERE scan_id = ? AND paper_id = ?""",
                        (
                            min(linked["position"], position),
                            max(linked["score"], incoming.score),
                            saved.scan_id,
                            stored.paper_id,
                        ),
                    )
            saved.papers = _linked_papers(connection, saved.scan_id)
        return saved

    def get_paper(self, paper_id: str) -> Paper | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT paper_id, payload FROM papers WHERE paper_id = ?", (paper_id,)
            ).fetchone()
            if row is None:
                row = connection.execute(
                    """SELECT papers.paper_id, papers.payload FROM paper_redirects
                       JOIN papers USING (paper_id) WHERE old_paper_id = ?""",
                    (paper_id,),
                ).fetchone()
        if row is None:
            return None
        paper = Paper.model_validate_json(row["payload"])
        paper.paper_id = row["paper_id"]
        return paper

    def get_scan(self, scan_id: str) -> SearchResult | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM search_scans WHERE scan_id = ?", (scan_id,)
            ).fetchone()
            if row is None:
                return None
            papers = _linked_papers(connection, scan_id)
        return SearchResult.model_validate(
            {
                "scan_id": row["scan_id"],
                "topic": row["topic"],
                "status": row["status"],
                "papers": papers,
                "provider_results": json.loads(row["provider_results"]),
            }
        )
