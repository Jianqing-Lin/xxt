import argparse
import csv
import sqlite3


def export_misses(db_path: str, output: str):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT question_hash, question, question_norm, options_json, options_norm_json,
                   type_code, source_kind, reason, source, updated_at
            FROM work_answer_misses
            ORDER BY updated_at DESC
            """
        ).fetchall()
    with open(output, "w", encoding="utf-8-sig", newline="") as writer:
        csv_writer = csv.writer(writer)
        csv_writer.writerow([
            "question_hash",
            "question",
            "question_norm",
            "options_json",
            "options_norm_json",
            "type_code",
            "source_kind",
            "reason",
            "source",
            "updated_at",
        ])
        for row in rows:
            csv_writer.writerow([row[key] for key in row.keys()])
    print(f"exported {len(rows)} miss record(s) to {output}")


def print_stats(db_path: str):
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("work_answers", "work_answer_misses", "problems"):
            if table in tables:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"{table}: {count}")


def main():
    parser = argparse.ArgumentParser(description="Autumn-xxt local tiku tools")
    parser.add_argument("--db", default="cxtk.db", help="SQLite database path")
    parser.add_argument("--export-misses", default="", help="Export misses to csv")
    parser.add_argument("--stats", action="store_true", help="Show local tiku stats")
    args = parser.parse_args()
    if args.stats:
        print_stats(args.db)
    if args.export_misses:
        export_misses(args.db, args.export_misses)


if __name__ == "__main__":
    main()
