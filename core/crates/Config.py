import json
import os
from typing import Any


def _ensure_parent_dir(file: str):
    directory = os.path.dirname(file)
    if directory:
        os.makedirs(directory, exist_ok=True)


def Write(file: str, text: Any) -> Any:
    _ensure_parent_dir(file)
    with open(file, 'w', encoding='utf-8') as w:
        json.dump(text, w, ensure_ascii=False, indent=2)
    return text


def Read(file: str) -> dict:
    _ensure_parent_dir(file)
    if not os.path.exists(file):
        return Write(file, {})
    try:
        with open(file, 'r', encoding='utf-8') as r:
            content = r.read().strip()
    except OSError:
        return Write(file, {})
    if not content:
        return Write(file, {})
    try:
        data = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return Write(file, {})
    if isinstance(data, dict):
        return data
    return Write(file, {})
