import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _now():
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self):
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    brief_json TEXT NOT NULL,
                    concepts_json TEXT NOT NULL,
                    selected_concept_id TEXT,
                    outline_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def create_project(self, project_id, brief, concepts):
        now = _now()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO projects VALUES (?, ?, ?, NULL, NULL, ?, ?)",
                (project_id, json.dumps(brief, ensure_ascii=False),
                 json.dumps(concepts, ensure_ascii=False), now, now),
            )
            conn.commit()
        finally:
            conn.close()

    def update_project(self, project_id, *, concepts=None, selected_concept_id=None,
                       outline=None, clear_outline=False):
        fields = ["updated_at = ?"]
        values = [_now()]
        if concepts is not None:
            fields.append("concepts_json = ?")
            values.append(json.dumps(concepts, ensure_ascii=False))
        if selected_concept_id is not None or clear_outline:
            fields.append("selected_concept_id = ?")
            values.append(selected_concept_id)
        if outline is not None or clear_outline:
            fields.append("outline_json = ?")
            values.append(None if clear_outline else json.dumps(outline, ensure_ascii=False))
        values.append(project_id)
        conn = self._connect()
        try:
            conn.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
        finally:
            conn.close()

    def get_project(self, project_id):
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return {
            "id": row["id"],
            "brief": json.loads(row["brief_json"]),
            "concepts": json.loads(row["concepts_json"]),
            "selected_concept_id": row["selected_concept_id"],
            "outline": json.loads(row["outline_json"]) if row["outline_json"] else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def log_run(self, project_id, action, status, provider, error=None):
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO runs (project_id, action, status, provider, error, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, action, status, provider, error, _now()),
            )
            conn.commit()
        finally:
            conn.close()

    def list_runs(self, project_id):
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, action, status, provider, error, created_at "
                "FROM runs WHERE project_id = ? ORDER BY id", (project_id,)
            ).fetchall()
        finally:
            conn.close()
        return [dict(row) for row in rows]
