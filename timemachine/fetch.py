"""Download revision history for the articles in articles.txt.

Usage:
    python -m timemachine.fetch                  # one revision per quarter (default)
    python -m timemachine.fetch --every month    # denser history, more data
    python -m timemachine.fetch --force          # re-download files that already exist

Writes one JSON file per article to data/raw/. Nothing here touches the database,
so the download only has to happen once and the load can be repeated offline.

Wikipedia articles can have tens of thousands of revisions, so we keep one per
period: the last revision of each month, quarter or year. "The article as of a
date" is then exact to within one period.
"""

import argparse
import json
import re
import time
from pathlib import Path

import requests

API = "https://en.wikipedia.org/w/api.php"
# Wikimedia asks API clients to identify themselves.
USER_AGENT = "wiki-timemachine/0.1 (student project; https://github.com/NicksZone/Databases-Project)"
ROOT = Path(__file__).resolve().parent.parent
ARTICLES_FILE = ROOT / "articles.txt"
RAW_DIR = ROOT / "data" / "raw"
CONTENT_BATCH = 20  # revisions per content request, keeps responses well under the API size limit

session = requests.Session()
session.headers["User-Agent"] = USER_AGENT


def api_get(params: dict) -> dict:
    params = {"action": "query", "format": "json", "formatversion": "2", **params}
    for attempt in range(5):
        resp = session.get(API, params=params, timeout=60)
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"Wikipedia API error: {data['error']}")
        return data
    raise RuntimeError(f"Wikipedia API kept failing for {params}")


def read_titles() -> list[str]:
    lines = ARTICLES_FILE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def list_revisions(title: str) -> tuple[int, str, list[dict]]:
    """All revision ids and timestamps of one article, oldest first (no text yet)."""
    params = {
        "prop": "revisions",
        "titles": title,
        "redirects": "1",
        "rvprop": "ids|timestamp",
        "rvlimit": "max",
        "rvdir": "newer",
    }
    revisions, page_id, real_title = [], None, title
    while True:
        data = api_get(params)
        page = data["query"]["pages"][0]
        if page.get("missing"):
            raise RuntimeError(f"No Wikipedia article called {title!r}")
        page_id, real_title = page["pageid"], page["title"]
        revisions += page.get("revisions", [])
        if "continue" not in data:
            return page_id, real_title, revisions
        params.update(data["continue"])


def period_key(timestamp: str, every: str) -> str:
    year, month = timestamp[:4], int(timestamp[5:7])
    if every == "year":
        return year
    if every == "quarter":
        return f"{year}-Q{(month - 1) // 3 + 1}"
    return timestamp[:7]


def pick_per_period(revisions: list[dict], every: str) -> list[int]:
    """The last revision id of each period. Revisions arrive oldest first."""
    last = {}
    for rev in revisions:
        last[period_key(rev["timestamp"], every)] = rev["revid"]
    return list(last.values())


def fetch_contents(rev_ids: list[int]) -> list[dict]:
    out = []
    for i in range(0, len(rev_ids), CONTENT_BATCH):
        params = {
            "prop": "revisions",
            "revids": "|".join(map(str, rev_ids[i:i + CONTENT_BATCH])),
            "rvprop": "ids|timestamp|user|comment|content",
            "rvslots": "main",
        }
        while True:
            data = api_get(params)
            for page in data["query"]["pages"]:
                for rev in page.get("revisions", []):
                    main = rev.get("slots", {}).get("main", {})
                    if "content" not in main:  # text hidden or deleted by Wikipedia
                        continue
                    out.append({
                        "rev_id": rev["revid"],
                        "timestamp": rev["timestamp"],
                        "user": rev.get("user"),  # absent when the user name is hidden
                        "comment": rev.get("comment"),
                        "content": main["content"],
                    })
            if "continue" not in data:
                break
            params.update(data["continue"])
    out.sort(key=lambda r: r["timestamp"])
    return out


def file_for(title: str) -> Path:
    return RAW_DIR / (re.sub(r"[^\w\-]+", "_", title) + ".json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--every", choices=["month", "quarter", "year"], default="quarter")
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for title in read_titles():
        target = file_for(title)
        if target.exists() and not args.force:
            print(f"skip   {title} (already in {target.relative_to(ROOT)})")
            continue
        page_id, real_title, all_revs = list_revisions(title)
        chosen = pick_per_period(all_revs, args.every)
        revisions = fetch_contents(chosen)
        target.write_text(json.dumps({
            "page_id": page_id,
            "title": real_title,
            "sampled_every": args.every,
            "total_revisions_on_wikipedia": len(all_revs),
            "revisions": revisions,
        }, ensure_ascii=False), encoding="utf-8")
        print(f"saved  {real_title}: {len(revisions)} of {len(all_revs)} revisions")


if __name__ == "__main__":
    main()
