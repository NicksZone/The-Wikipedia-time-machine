"""(Re)create the schema and load the downloaded revisions into MariaDB.

Usage:
    python -m timemachine.load

Run python -m timemachine.fetch first. Every run starts from an empty database,
so loading twice gives the same result as loading once.

How the history gets its real dates
-----------------------------------
A system-versioned table stamps each row version with the time the statement
ran. Loading revisions the naive way would give a perfect history of this
script, all of it from the last few seconds, and nothing about the article.

Instead we replay the revisions in order and, before each statement, set the
session clock to the moment the revision was made on Wikipedia:

    SET timestamp = <revision time>;
    UPDATE page_content SET content = ... WHERE page_id = ...;

The server then records that revision's period as starting at its real edit
time and ends the previous version at the same moment. MariaDB allows this
because secure_timestamp defaults to NO. On a server where it is set to YES,
this loader cannot work. See the README for the alternatives.
"""

import json
from datetime import datetime
from pathlib import Path

from timemachine.db import connect
from timemachine.fetch import RAW_DIR, ROOT

SCHEMA_FILE = ROOT / "sql" / "schema.sql"


def run_schema(cur) -> None:
    lines = [l for l in SCHEMA_FILE.read_text(encoding="utf-8").splitlines() if not l.strip().startswith("--")]
    for statement in "\n".join(lines).split(";"):
        if statement.strip():
            cur.execute(statement)


def unix_time(iso: str) -> float:
    # Wikipedia gives e.g. 2006-08-24T14:30:05Z
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def load_article(cur, path: Path) -> int:
    article = json.loads(path.read_text(encoding="utf-8"))
    page_id = article["page_id"]
    cur.execute("INSERT INTO pages (page_id, title) VALUES (?, ?)", (page_id, article["title"]))

    loaded, last_ts = 0, None
    for rev in article["revisions"]:
        ts = unix_time(rev["timestamp"])
        if last_ts is not None and ts <= last_ts:
            continue  # a version needs a period longer than zero
        cur.execute("SET timestamp = ?", (ts,))
        values = (rev["rev_id"], rev["user"], rev["comment"], rev["content"], page_id)
        if loaded == 0:
            cur.execute(
                "INSERT INTO page_content (rev_id, editor, edit_comment, content, page_id) VALUES (?, ?, ?, ?, ?)",
                values,
            )
        else:
            cur.execute(
                "UPDATE page_content SET rev_id = ?, editor = ?, edit_comment = ?, content = ? WHERE page_id = ?",
                values,
            )
        loaded, last_ts = loaded + 1, ts

    cur.execute("SET timestamp = DEFAULT")
    return loaded


def main() -> None:
    files = sorted(RAW_DIR.glob("*.json"))
    if not files:
        raise SystemExit("No data in data/raw/. Run: python -m timemachine.fetch")

    # Autocommit, so every statement is its own transaction and takes the
    # timestamp we just set.
    conn = connect(autocommit=True)
    cur = conn.cursor()
    run_schema(cur)
    print("schema created")

    total = 0
    for path in files:
        n = load_article(cur, path)
        total += n
        print(f"loaded {path.stem}: {n} versions")

    cur.execute("""
        SELECT MIN(sys_start), MAX(sys_start), COUNT(*)
        FROM page_content FOR SYSTEM_TIME ALL
    """)
    oldest, newest, rows = cur.fetchone()
    print(f"\n{total} versions of {len(files)} articles, {rows} rows in page_content")
    print(f"history spans {oldest} .. {newest} (UTC)")
    conn.close()


if __name__ == "__main__":
    main()
