"""Reconcile late identity bridges while preserving old IDs as redirects."""

import sqlite3

from litwatch.core import Paper
from litwatch.storage.identity import compatible, enrich


def _reparent(connection: sqlite3.Connection, old_id: str, canonical_id: str) -> None:
    links = connection.execute(
        "SELECT scan_id, position, score FROM scan_papers WHERE paper_id = ?", (old_id,)
    ).fetchall()
    for link in links:
        existing = connection.execute(
            "SELECT position, score FROM scan_papers WHERE scan_id = ? AND paper_id = ?",
            (link["scan_id"], canonical_id),
        ).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO scan_papers VALUES (?, ?, ?, ?)",
                (link["scan_id"], canonical_id, link["position"], link["score"]),
            )
        else:
            connection.execute(
                """UPDATE scan_papers SET position = ?, score = ?
                   WHERE scan_id = ? AND paper_id = ?""",
                (
                    min(existing["position"], link["position"]),
                    max(existing["score"], link["score"]),
                    link["scan_id"],
                    canonical_id,
                ),
            )
    connection.execute("DELETE FROM scan_papers WHERE paper_id = ?", (old_id,))
    connection.execute(
        "UPDATE paper_aliases SET paper_id = ? WHERE paper_id = ?", (canonical_id, old_id)
    )
    connection.execute(
        "UPDATE paper_redirects SET paper_id = ? WHERE paper_id = ?", (canonical_id, old_id)
    )
    connection.execute(
        "INSERT INTO paper_redirects VALUES (?, ?)", (old_id, canonical_id)
    )
    connection.execute("DELETE FROM papers WHERE paper_id = ?", (old_id,))


def reconcile(connection: sqlite3.Connection, matches: list[Paper]) -> Paper:
    if not matches:
        raise ValueError("cannot reconcile without identity matches")
    created = {
        row["paper_id"]: row["created_at"]
        for row in connection.execute(
            f"SELECT paper_id, created_at FROM papers WHERE paper_id IN ({','.join('?' for _ in matches)})",
            [item.paper_id for item in matches],
        )
    }
    preferred = matches[0]  # find_matches follows DOI → arXiv → provider priority
    canonical = (
        min(matches, key=lambda item: (created[item.paper_id], item.paper_id))
        if all(compatible(preferred, item, "provider") for item in matches)
        else preferred
    )
    for duplicate in matches:
        if duplicate.paper_id == canonical.paper_id or not compatible(
            canonical, duplicate, "provider"
        ):
            continue
        canonical = enrich(canonical, duplicate)
        _reparent(connection, duplicate.paper_id, canonical.paper_id)
    return canonical
