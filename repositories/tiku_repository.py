import sqlite3


class TikuRepository:
    def __init__(self, db_path: str = "cxtk.db"):
        self.db_path = db_path or "cxtk.db"

    def connect(self):
        return sqlite3.connect(self.db_path)

    def _ensure_column(self, conn, table: str, column: str, ddl: str):
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    def init_db(self):
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS work_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_hash TEXT NOT NULL UNIQUE,
                    question TEXT NOT NULL,
                    question_norm TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    options_norm_json TEXT NOT NULL,
                    type_code TEXT NOT NULL,
                    source_kind TEXT NOT NULL DEFAULT 'unknown',
                    answer TEXT NOT NULL,
                    answer_text TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'local',
                    correct_count INTEGER NOT NULL DEFAULT 1,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                )
                """
            )
            self._ensure_column(conn, "work_answers", "source_kind", "source_kind TEXT NOT NULL DEFAULT 'unknown'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_work_answers_question_norm ON work_answers(question_norm)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_work_answers_source_kind ON work_answers(source_kind)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS work_answer_misses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_hash TEXT NOT NULL,
                    question TEXT NOT NULL,
                    question_norm TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    options_norm_json TEXT NOT NULL,
                    type_code TEXT NOT NULL,
                    source_kind TEXT NOT NULL DEFAULT 'unknown',
                    reason TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'miss',
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                )
                """
            )
            self._ensure_column(conn, "work_answer_misses", "source_kind", "source_kind TEXT NOT NULL DEFAULT 'unknown'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_work_answer_misses_hash ON work_answer_misses(question_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_work_answer_misses_source_kind ON work_answer_misses(source_kind)")

    def list_tables(self) -> set[str]:
        with self.connect() as conn:
            return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def count_table(self, name: str) -> int:
        with self.connect() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]

    def fetch_legacy_problems(self) -> list[tuple[str, str]]:
        tables = self.list_tables()
        if "problems" not in tables:
            return []
        with self.connect() as conn:
            return conn.execute("SELECT question, answer FROM problems WHERE question != '' AND answer != ''").fetchall()

    def fetch_answer_by_hash(self, question_hash: str):
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM work_answers WHERE question_hash = ?",
                (question_hash,),
            ).fetchone()
            return dict(row) if row else None

    def fetch_answer_candidates(self, type_code: str, question_norm: str, source_kind: str, limit: int = 5):
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM work_answers WHERE type_code = ? AND question_norm = ? AND source_kind = ? ORDER BY correct_count DESC, updated_at DESC LIMIT ?",
                (str(type_code), question_norm, str(source_kind or "unknown"), limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def insert_missing(self, payload: tuple):
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO work_answer_misses (
                    question_hash, question, question_norm, options_json, options_norm_json,
                    type_code, source_kind, reason, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
                """,
                payload,
            )

    def list_answers(self, limit: int = 100, offset: int = 0) -> list[dict]:
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, question_hash, question, question_norm, options_json, options_norm_json,
                       type_code, source_kind, answer, answer_text, source, correct_count, updated_at
                FROM work_answers
                ORDER BY updated_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_answer(self, answer_id: int) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM work_answers WHERE id = ?", (int(answer_id),))
            return cursor.rowcount > 0

    def upsert_answer(self, payload: tuple):
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO work_answers (
                    question_hash, question, question_norm, options_json, options_norm_json,
                    type_code, source_kind, answer, answer_text, source, correct_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, strftime('%s','now'))
                ON CONFLICT(question_hash) DO UPDATE SET
                    source_kind = excluded.source_kind,
                    answer = excluded.answer,
                    answer_text = excluded.answer_text,
                    source = excluded.source,
                    correct_count = work_answers.correct_count + 1,
                    updated_at = strftime('%s','now')
                """,
                payload,
            )
