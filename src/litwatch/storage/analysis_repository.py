"""SQLite persistence for structured paper analyses."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from litwatch.analysis.models import PaperAnalysis, QuickScan
from litwatch.storage.database import Database


class AnalysisRepository:
    def __init__(self, path: str | Path) -> None:
        self.database = Database(path)

    def save(
        self,
        *,
        paper_id: str,
        analysis_mode: str,
        model: str,
        result: QuickScan,
    ) -> PaperAnalysis:
        analysis = PaperAnalysis(
            analysis_id=f"A-{uuid4().hex}",
            paper_id=paper_id,
            analysis_mode=analysis_mode,
            model=model,
            result=result,
            created_at=datetime.now(UTC).isoformat(),
        )
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO analyses VALUES (?, ?, ?, ?, ?, ?)",
                (
                    analysis.analysis_id,
                    analysis.paper_id,
                    analysis.analysis_mode,
                    analysis.model,
                    analysis.result.model_dump_json(),
                    analysis.created_at,
                ),
            )
        return analysis

    def get(self, analysis_id: str) -> PaperAnalysis | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM analyses WHERE analysis_id = ?", (analysis_id,)
            ).fetchone()
        if row is None:
            return None
        return PaperAnalysis.model_validate(
            {
                "analysis_id": row["analysis_id"],
                "paper_id": row["paper_id"],
                "analysis_mode": row["analysis_mode"],
                "model": row["model"],
                "result": QuickScan.model_validate_json(row["result_json"]),
                "created_at": row["created_at"],
            }
        )
