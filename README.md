A project for area 3, "System-versioned tables: history for free" for the [MariaDB student database projects, 2026-09](https://mariadb.org/bachelor_hackathon_2026-09/).

# Wikipedia Time Machine

Pick a Wikipedia article and a moment in time, and see the article as it stood then. The history is kept by MariaDB itself: one `WITH SYSTEM VERSIONING` clause on a table, read back with `FOR SYSTEM_TIME AS OF`. There are no revision tables, no triggers and no history code in the application.

There's an irony here. Wikipedia runs on MariaDB, but it keeps its history in application-level revision tables that were designed years before system versioning existed. This project lets the database do that job in one clause.

Developed against **MariaDB 12.3.3** (LTS) on Windows 11, with Python 3.13.

## Quick start

Requirements: MariaDB 12.3 (11.8 or later should also work) and Python 3.11 or later.

1. Create a database and a user (in `mariadb -u root -p`):
   ```sql
   CREATE DATABASE wiki_timemachine CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'wiki'@'localhost' IDENTIFIED BY 'choose-a-password';
   GRANT ALL ON wiki_timemachine.* TO 'wiki'@'localhost';
   ```
2. Install and configure:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   copy .env.example .env        # macOS/Linux: cp .env.example .env, then set DB_PASSWORD
   ```
3. Download the revisions, load them, and start the page:
   ```bash
   python -m timemachine.fetch     # about 20 articles, one revision per quarter, saved to data/raw/
   python -m timemachine.load      # recreates the schema and replays the history
   flask --app timemachine.web run # open http://127.0.0.1:5000
   ```

Try **Pluto** around 24 August 2006, the day it stopped being a planet. Then open **Compare** to see June 2006 against January 2007: "the traditional ninth planet" turns into "the second-largest known dwarf planet".

The Compare page runs a single query that reads `page_content` at two moments and joins it to itself. See `ARTICLE_AT_TWO_MOMENTS` in [`timemachine/queries.py`](timemachine/queries.py).

## Data

The data is the article list in [`articles.txt`](articles.txt), fetched from the MediaWiki API by `timemachine/fetch.py`. Popular articles have tens of thousands of revisions, so the fetcher keeps **the last revision of each quarter** (or each month or year, with `--every`). "As of a date" is therefore exact to within one period. Every revision that is kept has its real Wikipedia timestamp.

## Data model

See [`sql/schema.sql`](sql/schema.sql).

| table | engine / options | holds |
|---|---|---|
| `pages` | InnoDB, not versioned | one row per article: `page_id`, `title` |
| `page_content` | InnoDB, `WITH SYSTEM VERSIONING` | the current text of each article, plus every earlier version, kept by the server |

Why two tables:
- The title is identity, and the text is what changes. Only the text needs a history, so only `page_content` pays the storage cost of versioning.
- The period columns `sys_start` and `sys_end` are declared explicitly so that queries and the web page can show them. They are `INVISIBLE`, so `SELECT *` still looks like an ordinary table.

## The real design question: whose timestamps?

System versioning stamps a row with the time the statement ran. A naive import therefore records a perfect history of the loading script and nothing about the article. The options are:

1. **Replay with import-time stamps.** This is simple, but the dates are wrong.
2. **Replay with the session clock set to each revision's real time.** This is what the loader does now:
   ```sql
   SET timestamp = UNIX_TIMESTAMP('2006-08-24 14:30:05');
   UPDATE page_content SET content = ... WHERE page_id = ...;
   ```
   The server ends the previous version and starts the new one at the real edit time. This only works while `secure_timestamp` is `NO` (the default), and that setting exists precisely because this technique can fake history.
3. **Write history rows directly** with `system_versioning_insert_history`.
4. **An application-time period** for the edit dates, kept next to the system period. The system period then means "when we loaded it", and the application period means "when it was true on Wikipedia".

_TODO: compare 3 and 4 against 2, and explain the final choice._

## Example queries

See [`sql/examples.sql`](sql/examples.sql) for queries you can paste into the client: `AS OF`, `BETWEEN`, `ALL`, and a history-size breakdown. All of the SQL the web app runs is in [`timemachine/queries.py`](timemachine/queries.py).

## Project layout

```
articles.txt              the fixed set of articles
sql/schema.sql            the two tables (the important file)
sql/examples.sql          queries to paste into the mariadb client
timemachine/fetch.py      MediaWiki API -> data/raw/*.json
timemachine/load.py       data/raw -> MariaDB, replaying history with real timestamps
timemachine/queries.py    every SQL statement the web app uses
timemachine/render.py     wikitext -> readable paragraphs, and the paragraph/word diff
timemachine/web.py        Flask app: / (read as of a moment) and /diff (compare two moments)
timemachine/templates/    the pages
timemachine/static/       stylesheet
```

## Roadmap

- [x] Show a diff between two chosen moments
- [ ] Measure how the versioned table grows (rows and bytes per article, current vs history)
- [ ] `PARTITION BY SYSTEM_TIME` to keep current rows apart from history, and measure the effect
- [ ] Alternatives 3 and 4 above, compared
- [ ] Where history in the database stops being the right answer

## Team

Nikolozi Barkalaia (solo)
