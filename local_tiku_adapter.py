import json
import sqlite3
from typing import Any

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

from services.tiku_service import TikuService


app = FastAPI(title="Autumn local tiku adapter", version="0.1.0")
service = TikuService(db_path="cxtk.db", adapter_url="", use="", tokens={})


class AdapterSearchRequest(BaseModel):
    qid: str | int | None = ""
    plat: int | None = 0
    question: str = ""
    options: list[str] = Field(default_factory=list)
    type: int | str = 4


def normalize_type_code(value: int | str | None) -> str:
    text = str(value if value is not None else "4").strip()
    return text if text in {"0", "1", "2", "3", "4"} else "4"


def load_candidates(question_norm: str, type_code: str) -> list[dict[str, Any]]:
    with service.repository.connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM work_answers
            WHERE type_code = ? AND question_norm = ?
            ORDER BY correct_count DESC, updated_at DESC, id DESC
            """,
            (type_code, question_norm),
        ).fetchall()
        if not rows:
            rows = conn.execute(
                """
                SELECT * FROM work_answers
                WHERE question_norm = ?
                ORDER BY correct_count DESC, updated_at DESC, id DESC
                LIMIT 20
                """,
                (question_norm,),
            ).fetchall()
        return [dict(row) for row in rows]


def select_best_candidate(candidates: list[dict[str, Any]], normalized_options: list[str]) -> dict[str, Any] | None:
    if not candidates:
        return None

    def score(row: dict[str, Any]):
        stored_options = json.loads(row.get("options_norm_json") or "[]")
        exact = int(stored_options == normalized_options)
        overlap = len([item for item in stored_options if item in normalized_options])
        option_shape = int(not normalized_options or not stored_options)
        return (
            exact,
            overlap,
            option_shape,
            int(row.get("correct_count") or 0),
            int(row.get("updated_at") or 0),
            int(row.get("id") or 0),
        )

    return max(candidates, key=score)


def build_adapter_answer_payload(row: dict[str, Any]) -> dict[str, Any]:
    answer = str(row.get("answer") or "").strip()
    answer_text = str(row.get("answer_text") or "").strip()
    type_code = str(row.get("type_code") or "4")
    if type_code in {"0", "1"}:
        keys = [char for char in answer.upper() if "A" <= char <= "Z"]
        answer_key: str | list[str] = ""
        if len(keys) == 1:
            answer_key = keys[0]
        elif len(keys) > 1:
            answer_key = keys
        return {
            "answerKey": answer_key,
            "answercontent": answer_text or answer,
            "answerText": answer_text or answer,
            "content": answer_text or answer,
        }
    if type_code == "3":
        content = answer_text or ("正确" if answer.lower() == "true" else "错误" if answer.lower() == "false" else answer)
        return {
            "content": content,
            "answercontent": content,
            "answerText": content,
        }
    content = answer_text or answer
    return {
        "content": content,
        "bestAnswer": content,
        "answercontent": content,
        "answerText": content,
    }


def query_local_adapter(payload: AdapterSearchRequest) -> dict[str, Any]:
    question_norm = service.normalize_text(payload.question)
    type_code = normalize_type_code(payload.type)
    normalized_options = [service.strip_option_prefix(option) for option in (payload.options or [])]
    candidates = load_candidates(question_norm, type_code)
    matched = select_best_candidate(candidates, normalized_options)
    if not matched:
        return {
            "code": 0,
            "msg": "not found",
            "data": {"answer": {}},
        }
    return {
        "code": 1,
        "msg": "ok",
        "data": {
            "answer": build_adapter_answer_payload(matched),
            "source": matched.get("source", "local"),
            "question_hash": matched.get("question_hash", ""),
            "source_kind": matched.get("source_kind", "unknown"),
            "type_code": matched.get("type_code", "4"),
        },
    }


@app.get("/health")
def health():
    return {"ok": True, "tables": sorted(service.repository.list_tables())}


@app.post("/adapter-service/search")
def adapter_service_search(payload: AdapterSearchRequest):
    return query_local_adapter(payload)


if __name__ == "__main__":
    print("Autumn local tiku adapter starting at http://127.0.0.1:8060/")
    uvicorn.run("local_tiku_adapter:app", host="127.0.0.1", port=8060, reload=False)
