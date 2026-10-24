"""The time machine page: pick an article and a moment, see the article as it was.

Run:
    flask --app timemachine.web run
then open http://127.0.0.1:5000
"""

from datetime import datetime, timezone

import mwparserfromhell
from flask import Flask, render_template, request

from timemachine import queries
from timemachine.db import connect

app = Flask(__name__)


def parse_moment(value: str | None) -> datetime:
    """Accepts what <input type="datetime-local"> sends, e.g. 2006-06-01T12:00. Defaults to now."""
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value or "", fmt)
        except ValueError:
            pass
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def to_plain_text(wikitext: str) -> list[str]:
    """Wikitext -> readable paragraphs. Templates such as infoboxes are dropped."""
    text = mwparserfromhell.parse(wikitext).strip_code(normalize=True, collapse=True)
    return [p.strip() for p in text.split("\n\n") if p.strip()]


@app.route("/")
def index():
    moment = parse_moment(request.args.get("at"))

    conn = connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(queries.LIST_ARTICLES)
        titles = [row["title"] for row in cur.fetchall()]
        title = request.args.get("title") or (titles[0] if titles else None)

        version, versions = None, []
        if title:
            cur.execute(queries.ARTICLE_AS_OF, (moment.strftime("%Y-%m-%d %H:%M:%S"), title))
            version = cur.fetchone()
            cur.execute(queries.ARTICLE_VERSIONS, (title,))
            versions = cur.fetchall()
    finally:
        conn.close()

    return render_template(
        "index.html",
        titles=titles,
        title=title,
        moment=moment,
        version=version,
        paragraphs=to_plain_text(version["content"]) if version else [],
        versions=versions,
        query=queries.ARTICLE_AS_OF.strip(),
    )
