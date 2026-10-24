"""One place that knows how to connect to MariaDB, configured from .env."""

import os

import mariadb
from dotenv import load_dotenv

load_dotenv()


def connect(autocommit: bool = False) -> mariadb.Connection:
    password = os.getenv("DB_PASSWORD")
    if not password:
        raise SystemExit("DB_PASSWORD is not set. Copy .env.example to .env and fill it in.")

    conn = mariadb.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "wiki"),
        password=password,
        database=os.getenv("DB_NAME", "wiki_timemachine"),
        autocommit=autocommit,
    )
    # Every timestamp in this project is UTC: Wikipedia's revision times, the
    # system period columns, and the dates typed into the web page.
    cur = conn.cursor()
    cur.execute("SET time_zone = '+00:00'")
    cur.close()
    return conn
