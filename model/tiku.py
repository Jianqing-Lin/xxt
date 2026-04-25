import hashlib
import json
import re
import sqlite3
import string
from difflib import SequenceMatcher
from typing import Optional

from core.crates.Http import Http


class TikuStore:
    TYPE_MAP = {
        "0": 0,  # 单选
        "1": 1,  # 多选
        "2": 2,  # 填空
        "3": 3,  # 判断
        "4": 4,  # 简答
    }

    def __init__(self, db_path="cxtk.db", adapter_url="http://localhost:8060/adapter-service/search", use="local,icodef,buguake", tokens=None, proxy=None):
        self.db_path = db_path or "cxtk.db"
        self.adapter_url = adapter_url
        self.use = use
        self.tokens = tokens or {}
        self.proxy = proxy
        self.last_error = ""
        self.last_payload = None
        self._init_db()
        self.import_legacy_problems()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
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
                    answer TEXT NOT NULL,
                    answer_text TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'local',
                    correct_count INTEGER NOT NULL DEFAULT 1,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_work_answers_question_norm ON work_answers(question_norm)")
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
                    reason TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'miss',
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_work_answer_misses_hash ON work_answer_misses(question_hash)")

    def stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            work_count = conn.execute("SELECT COUNT(*) FROM work_answers").fetchone()[0]
            miss_count = conn.execute("SELECT COUNT(*) FROM work_answer_misses").fetchone()[0]
            legacy_count = 0
            if "problems" in tables:
                legacy_count = conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0]
            return {"work_answers": work_count, "work_answer_misses": miss_count, "legacy_problems": legacy_count}

    def import_legacy_problems(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "problems" not in tables:
                return 0
            rows = conn.execute("SELECT question, answer FROM problems WHERE question != '' AND answer != ''").fetchall()
        imported = 0
        for question, answer in rows:
            q = {
                "id": "legacy",
                "title": question,
                "options": [],
                "type_code": "4",
            }
            before = self.get_local(q)
            self.save(q, answer, answer, source="legacy-problems")
            if before is None:
                imported += 1
        return imported

    def normalize_text(self, value: str) -> str:
        if value is None:
            return ""
        value = str(value).strip()
        table = str.maketrans({
            "“": '"', "”": '"', "‘": "'", "’": "'", "。": ".", "　": " ",
        })
        value = value.translate(table).replace("&nbsp;", " ")
        value = re.sub(r"\s+", " ", value)
        return value.strip().strip(",.?:!;，。？：！；")

    def strip_option_prefix(self, value: str) -> str:
        value = self.normalize_text(value)
        return re.sub(r"^[A-Za-z][\.．:：、\s]+", "", value).strip()

    def normalized_options(self, question: dict) -> list[str]:
        return [self.strip_option_prefix(option) for option in question.get("options", [])]

    def question_hash(self, question: dict) -> str:
        payload = {
            "question": self.normalize_text(question.get("title", "")),
            "options": self.normalized_options(question),
            "type": str(question.get("type_code", "")),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def type_to_adapter(self, type_code: str) -> int:
        return self.TYPE_MAP.get(str(type_code), 4)

    def split_answer_text(self, value: str) -> list[str]:
        if not value:
            return []
        parts = re.split(r"[#|,，;；\n\r\t、]+", str(value))
        return [self.normalize_text(part) for part in parts if self.normalize_text(part)]

    def get_local(self, question: dict) -> Optional[dict]:
        qhash = self.question_hash(question)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM work_answers WHERE question_hash = ?",
                (qhash,),
            ).fetchone()
            if row:
                return dict(row)

            qnorm = self.normalize_text(question.get("title", ""))
            candidates = conn.execute(
                "SELECT * FROM work_answers WHERE type_code = ? AND question_norm = ? ORDER BY correct_count DESC, updated_at DESC LIMIT 5",
                (str(question.get("type_code", "")), qnorm),
            ).fetchall()
            current_options = self.normalized_options(question)
            for candidate in candidates:
                stored_options = json.loads(candidate["options_norm_json"] or "[]")
                if stored_options == current_options:
                    return dict(candidate)
        return None

    def save_missing(self, question: dict, reason: str = "", source: str = "miss"):
        qhash = self.question_hash(question)
        qnorm = self.normalize_text(question.get("title", ""))
        options = list(question.get("options", []))
        options_norm = self.normalized_options(question)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO work_answer_misses (
                    question_hash, question, question_norm, options_json, options_norm_json,
                    type_code, reason, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
                """,
                (
                    qhash,
                    question.get("title", ""),
                    qnorm,
                    json.dumps(options, ensure_ascii=False),
                    json.dumps(options_norm, ensure_ascii=False),
                    str(question.get("type_code", "")),
                    reason,
                    source,
                ),
            )

    def save(self, question: dict, answer: str, answer_text: str = "", source: str = "manual"):
        answer = str(answer or "").strip()
        if not answer:
            return
        qhash = self.question_hash(question)
        qnorm = self.normalize_text(question.get("title", ""))
        options = list(question.get("options", []))
        options_norm = self.normalized_options(question)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO work_answers (
                    question_hash, question, question_norm, options_json, options_norm_json,
                    type_code, answer, answer_text, source, correct_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, strftime('%s','now'))
                ON CONFLICT(question_hash) DO UPDATE SET
                    answer = excluded.answer,
                    answer_text = excluded.answer_text,
                    source = excluded.source,
                    correct_count = work_answers.correct_count + 1,
                    updated_at = strftime('%s','now')
                """,
                (
                    qhash,
                    question.get("title", ""),
                    qnorm,
                    json.dumps(options, ensure_ascii=False),
                    json.dumps(options_norm, ensure_ascii=False),
                    str(question.get("type_code", "")),
                    answer,
                    answer_text,
                    source,
                ),
            )

    def query_adapter(self, question: dict) -> Optional[dict]:
        self.last_error = ""
        self.last_payload = None
        if not self.adapter_url:
            self.last_error = "adapter url empty"
            return None
        params = {"noRecord": "1"}
        if self.use:
            params["use"] = self.use
        params.update(self.tokens)
        payload = {
            "qid": question.get("id", ""),
            "plat": 0,
            "question": self.normalize_text(question.get("title", "")),
            "options": self.normalized_options(question),
            "type": self.type_to_adapter(question.get("type_code", "")),
        }
        try:
            with Http.Client(proxies=self.proxy, follow_redirects=True, timeout=12) as client:
                response = client.post(self.adapter_url, params=params, json=payload)
        except Exception as exc:
            self.last_error = f"adapter request failed: {exc}"
            return None
        if response.status_code != 200:
            self.last_error = f"adapter status {response.status_code}: {response.text[:200]}"
            return None
        try:
            self.last_payload = response.json()
            return self.last_payload
        except ValueError:
            self.last_error = f"adapter invalid json: {response.text[:200]}"
            return None

    def is_answer_shape_valid(self, question: dict, answer: str) -> bool:
        qtype = str(question.get("type_code", ""))
        answer = str(answer or "").strip()
        if not answer:
            return False
        if qtype == "0":
            return len(answer) == 1 and answer in string.ascii_uppercase
        if qtype == "1":
            return all(char in string.ascii_uppercase for char in answer) and len(set(answer)) == len(answer)
        if qtype == "3":
            return answer in {"true", "false"}
        return True

    def match_adapter_answer(self, question: dict, payload: dict) -> tuple[str, str]:
        answer = (payload or {}).get("answer", {}) or {}
        qtype = str(question.get("type_code", ""))
        if qtype in {"0", "1"}:
            keys = answer.get("answerKey") or []
            if keys:
                letters = [str(key).strip().upper() for key in keys if str(key).strip().upper() in string.ascii_uppercase]
                return "".join(sorted(set(letters))), "#".join(answer.get("bestAnswer") or [])

            candidates = answer.get("bestAnswer") or self.split_answer_text(answer.get("answerText", ""))
            options = self.normalized_options(question)
            matched = []
            for candidate in candidates:
                target = self.strip_option_prefix(candidate)
                best_index = -1
                best_score = 0.0
                for index, option in enumerate(options):
                    if option == target:
                        best_index, best_score = index, 1.0
                        break
                    score = SequenceMatcher(None, option, target).ratio()
                    if score > best_score:
                        best_index, best_score = index, score
                if best_index >= 0 and best_score >= 0.88:
                    matched.append(string.ascii_uppercase[best_index])
            return "".join(sorted(set(matched))), "#".join(candidates)

        if qtype == "3":
            text = "#".join(answer.get("bestAnswer") or []) + "#" + str(answer.get("answerText", ""))
            if re.search(r"正确|是|对|√|true|\bT\b|\bA\b", text, re.I):
                return "true", text
            if re.search(r"错误|否|错|×|false|\bF\b|\bB\b", text, re.I):
                return "false", text
            return "", text

        best = answer.get("bestAnswer") or self.split_answer_text(answer.get("answerText", ""))
        return "\n".join(best).strip(), "#".join(best)

    def query(self, question: dict) -> tuple[str, str, str]:
        local = self.get_local(question)
        if local:
            return local.get("answer", ""), local.get("answer_text", ""), "local"
        payload = self.query_adapter(question)
        if not payload:
            return "", "", f"none:{self.last_error or 'adapter no payload'}"
        answer, answer_text = self.match_adapter_answer(question, payload)
        if self.is_answer_shape_valid(question, answer):
            return answer, answer_text, "adapter"
        return "", answer_text, "adapter-empty: answer not matched to question/options"
