import json
def Write(file: str, text: dict) -> dict:
    with open(file, 'w+', encoding='utf-8') as w:
        w.write(json.dumps(text, ensure_ascii=False))
    return text
def Read(file: str) -> dict:
    try:
        with open(file, 'r+', encoding='utf-8') as r:
            return json.loads(r.read())
    except:
        return Write(file, {})

