"""The time machine pages.

    /       pick an article and a moment, see the article as it was
    /diff   pick an article and two moments, see what changed in between

Run:
    flask --app timemachine.web run
then open http://127.0.0.1:5000
"""

from datetime import datetime, timedelta, timezone

from flask import Flask, render_template, request

from timemachine import queries
from timemachine.db import connect
from timemachine.render import diff, to_paragraphs

app = Flask(__name__)


def parse_moment(value: str | None, default: datetime | None = None) -> datetime:
    """Accepts what <input type="datetime-local"> sends, e.g. 2006-06-01T12:00. Defaults to now."""
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value or "", fmt)
        except ValueError:
            pass
    return default or datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def sql_time(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def iso_utc(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def list_titles(cur) -> list[str]:
    cur.execute(queries.LIST_ARTICLES)
    return [row["title"] for row in cur.fetchall()]


@app.route("/")
def index():
    moment = parse_moment(request.args.get("at"))

    conn = connect()
    try:
        cur = conn.cursor(dictionary=True)
        titles = list_titles(cur)
        title = request.args.get("title") or (titles[0] if titles else None)

        version, versions = None, []
        if title:
            cur.execute(queries.ARTICLE_AS_OF, (sql_time(moment), title))
            version = cur.fetchone()
            cur.execute(queries.ARTICLE_VERSIONS, (title,))
            versions = cur.fetchall()
    finally:
        conn.close()

    # Everything the timeline scrubber (static/app.js) needs, embedded as JSON.
    timeline = {
        "title": title,
        "moment": iso_utc(moment),
        "now": iso_utc(parse_moment(None)),
        "current_rev": version["rev_id"] if version else None,
        "versions": [{"t": iso_utc(v["sys_start"]), "bytes": v["bytes"], "rev": v["rev_id"]} for v in versions],
    }

    return render_template(
        "index.html",
        titles=titles,
        title=title,
        moment=moment,
        version=version,
        paragraphs=to_paragraphs(version["content"]) if version else [],
        versions=versions,
        timeline=timeline,
        query=queries.ARTICLE_AS_OF.strip(),
    )


@app.route("/diff")
def compare():
    now = parse_moment(None)
    to_moment = parse_moment(request.args.get("to"), now)
    from_moment = parse_moment(request.args.get("from"), to_moment - timedelta(days=365))
    if from_moment > to_moment:
        from_moment, to_moment = to_moment, from_moment

    conn = connect()
    try:
        cur = conn.cursor(dictionary=True)
        titles = list_titles(cur)
        title = request.args.get("title") or (titles[0] if titles else None)
        row = None
        if title:
            cur.execute(queries.ARTICLE_AT_TWO_MOMENTS, (sql_time(from_moment), sql_time(to_moment), title))
            row = cur.fetchone()
    finally:
        conn.close()

    result = None
    if row and row["old_content"] is not None and row["new_content"] is not None:
        result = diff(row["old_content"], row["new_content"])

    return render_template(
        "diff.html",
        titles=titles,
        title=title,
        from_moment=from_moment,
        to_moment=to_moment,
        row=row,
        result=result,
        query=queries.ARTICLE_AT_TWO_MOMENTS.strip(),
    )
