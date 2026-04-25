import argparse
import csv
import json
import sqlite3


def export_misses(db_path: str, output: str, limit: int):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, question, options_json, type_code, reason, source, updated_at
            FROM work_answer_misses
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    with open(output, "w", encoding="utf-8-sig", newline="") as writer:
        fieldnames = ["id", "question", "options", "type_code", "reason", "source", "updated_at"]
        csv_writer = csv.DictWriter(writer, fieldnames=fieldnames)
        csv_writer.writeheader()
        for row in rows:
            try:
                options = " | ".join(json.loads(row["options_json"] or "[]"))
            except ValueError:
                options = row["options_json"]
            csv_writer.writerow(
                {
                    "id": row["id"],
                    "question": row["question"],
                    "options": options,
                    "type_code": row["type_code"],
                    "reason": row["reason"],
                    "source": row["source"],
                    "updated_at": row["updated_at"],
                }
            )
    print(f"exported {len(rows)} miss record(s) to {output}")


def show_stats(db_path: str):
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ["work_answers", "work_answer_misses", "problems"]:
            if table in tables:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"{table}: {count}")


def main():
    parser = argparse.ArgumentParser(description="xxt local tiku tools")
    parser.add_argument("--db", default="cxtk.db", help="SQLite database path")
    parser.add_argument("--export-misses", default="", help="Export missed questions to CSV")
    parser.add_argument("--limit", type=int, default=500, help="Max rows to export")
    args = parser.parse_args()
    show_stats(args.db)
    if args.export_misses:
        export_misses(args.db, args.export_misses, args.limit)


if __name__ == "__main__":
    main()
