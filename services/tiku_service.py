import hashlib
import json
import re
import string
from difflib import SequenceMatcher
from typing import Optional

from adapters.tiku_adapter_client import TikuAdapterClient
from repositories.tiku_repository import TikuRepository


class TikuService:
    TYPE_MAP = {
        "0": 0,
        "1": 1,
        "2": 2,
        "3": 3,
        "4": 4,
    }

    def __init__(self, db_path="cxtk.db", adapter_url="http://localhost:8060/adapter-service/search", use="local,icodef,buguake", tokens=None, proxy=None):
        self.repository = TikuRepository(db_path)
        self.adapter = TikuAdapterClient(adapter_url, use=use, tokens=tokens, proxy=proxy)
        self.last_error = ""
        self.last_payload = None
        self.repository.init_db()
        self.import_legacy_problems()

    def stats(self) -> dict:
        tables = self.repository.list_tables()
        work_count = self.repository.count_table("work_answers")
        miss_count = self.repository.count_table("work_answer_misses")
        legacy_count = self.repository.count_table("problems") if "problems" in tables else 0
        return {"work_answers": work_count, "work_answer_misses": miss_count, "legacy_problems": legacy_count}

    def import_legacy_problems(self) -> int:
        rows = self.repository.fetch_legacy_problems()
        imported = 0
        for question, answer in rows:
            q = {
                "id": "legacy",
                "title": question,
                "options": [],
                "type_code": "4",
                "source_kind": "unknown",
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

    def source_kind(self, question: dict) -> str:
        return str(question.get("source_kind") or "unknown")

    def question_hash(self, question: dict) -> str:
        payload = {
            "question": self.normalize_text(question.get("title", "")),
            "options": self.normalized_options(question),
            "type": str(question.get("type_code", "")),
            "source_kind": self.source_kind(question),
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
        row = self.repository.fetch_answer_by_hash(qhash)
        if row:
            return row
        qnorm = self.normalize_text(question.get("title", ""))
        candidates = self.repository.fetch_answer_candidates(
            str(question.get("type_code", "")),
            qnorm,
            self.source_kind(question),
        )
        current_options = self.normalized_options(question)
        for candidate in candidates:
            stored_options = json.loads(candidate["options_norm_json"] or "[]")
            if stored_options == current_options:
                return candidate
        return None

    def save_missing(self, question: dict, reason: str = "", source: str = "miss"):
        qhash = self.question_hash(question)
        qnorm = self.normalize_text(question.get("title", ""))
        options = list(question.get("options", []))
        options_norm = self.normalized_options(question)
        self.repository.insert_missing(
            (
                qhash,
                question.get("title", ""),
                qnorm,
                json.dumps(options, ensure_ascii=False),
                json.dumps(options_norm, ensure_ascii=False),
                str(question.get("type_code", "")),
                self.source_kind(question),
                reason,
                source,
            )
        )

    def save(self, question: dict, answer: str, answer_text: str = "", source: str = "manual"):
        answer = str(answer or "").strip()
        if not answer:
            return
        qhash = self.question_hash(question)
        qnorm = self.normalize_text(question.get("title", ""))
        options = list(question.get("options", []))
        options_norm = self.normalized_options(question)
        self.repository.upsert_answer(
            (
                qhash,
                question.get("title", ""),
                qnorm,
                json.dumps(options, ensure_ascii=False),
                json.dumps(options_norm, ensure_ascii=False),
                str(question.get("type_code", "")),
                self.source_kind(question),
                answer,
                answer_text,
                source,
            )
        )

    def query_adapter(self, question: dict) -> Optional[dict]:
        payload = {
            "qid": question.get("id", ""),
            "plat": 0,
            "question": self.normalize_text(question.get("title", "")),
            "options": self.normalized_options(question),
            "type": self.type_to_adapter(question.get("type_code", "")),
        }
        result = self.adapter.query(payload)
        self.last_error = self.adapter.last_error
        self.last_payload = self.adapter.last_payload
        return result

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

    def _payload_answer(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            return {}
        answer = payload.get("answer")
        if isinstance(answer, dict) and answer:
            return answer
        for key in ("data", "result", "obj"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                nested_answer = nested.get("answer")
                if isinstance(nested_answer, dict) and nested_answer:
                    return nested_answer
                if any(field in nested for field in ("answerKey", "bestAnswer", "answerText", "answerkey", "answercontent", "content")):
                    return nested
        if any(field in payload for field in ("answerKey", "bestAnswer", "answerText", "answerkey", "answercontent", "content")):
            return payload
        return {}

    def _answer_keys(self, answer: dict) -> list[str]:
        raw = answer.get("answerKey")
        if raw is None:
            raw = answer.get("answerkey")
        if raw is None:
            raw = answer.get("option")
        if raw is None:
            return []
        if isinstance(raw, str):
            values = self.split_answer_text(raw)
        elif isinstance(raw, list):
            values = [str(item).strip() for item in raw if str(item).strip()]
        else:
            values = [str(raw).strip()] if str(raw).strip() else []
        return values

    def _best_answers(self, answer: dict) -> list[str]:
        raw = answer.get("bestAnswer")
        if raw is None:
            raw = answer.get("bestanswer")
        if raw is None:
            raw = answer.get("content")
        if raw is None:
            raw = answer.get("answercontent")
        if raw is None:
            raw = answer.get("answer_text")
        if raw is None:
            return []
        if isinstance(raw, list):
            return [self.normalize_text(item) for item in raw if self.normalize_text(item)]
        return self.split_answer_text(raw)

    def _answer_text_value(self, answer: dict) -> str:
        for key in ("answerText", "answertext", "answer_text", "content", "answercontent", "msg"):
            value = answer.get(key)
            if value is None:
                continue
            if isinstance(value, list):
                return "#".join(self.normalize_text(item) for item in value if self.normalize_text(item))
            return str(value)
        return ""

    def match_adapter_answer(self, question: dict, payload: dict) -> tuple[str, str]:
        answer = self._payload_answer(payload)
        qtype = str(question.get("type_code", ""))
        if qtype in {"0", "1"}:
            keys = self._answer_keys(answer)
            if keys:
                letters = [str(key).strip().upper() for key in keys if str(key).strip().upper() in string.ascii_uppercase]
                return "".join(sorted(set(letters))), "#".join(self._best_answers(answer) or keys)
            candidates = self._best_answers(answer) or self.split_answer_text(self._answer_text_value(answer))
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
            best = self._best_answers(answer)
            text = "#".join(best) + "#" + self._answer_text_value(answer)
            if re.search(r"正确|是|对|√|true|\bT\b|\bA\b", text, re.I):
                return "true", text
            if re.search(r"错误|否|错|×|false|\bF\b|\bB\b", text, re.I):
                return "false", text
            return "", text
        best = self._best_answers(answer) or self.split_answer_text(self._answer_text_value(answer))
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
        return "", answer_text, f"adapter-empty:{self.last_error or 'answer not matched to question/options'}"
