"""Persist search snapshots and paper records without searching providers."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from litwatch.core import Paper, SearchResult
from litwatch.core.identity import normalized_title
from litwatch.storage.database import Database


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
                paper.paper_id = f"P-{uuid4().hex}"
                connection.execute(
                    "INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        paper.paper_id,
                        normalized_title(paper.title),
                        paper.doi,
                        paper.arxiv_id,
                        paper.model_dump_json(exclude={"paper_id"}),
                        now,
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO scan_papers VALUES (?, ?, ?, ?)",
                    (saved.scan_id, paper.paper_id, position, paper.score),
                )
        return saved

    def get_paper(self, paper_id: str) -> Paper | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT paper_id, payload FROM papers WHERE paper_id = ?", (paper_id,)
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
        return SearchResult.model_validate(
            {
                "scan_id": row["scan_id"],
                "topic": row["topic"],
                "status": row["status"],
                "papers": papers,
                "provider_results": json.loads(row["provider_results"]),
            }
        )
