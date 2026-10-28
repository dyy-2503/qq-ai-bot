"""B站视频库的 SQLite 存储层。"""

import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate (
    bvid          TEXT PRIMARY KEY,
    first_seen_at INTEGER NOT NULL,
    title         TEXT,
    up_name       TEXT,
    view          INTEGER,
    pubdate       INTEGER,
    decision      TEXT,
    reason        TEXT,
    judged_at     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_candidate_seen ON candidate(first_seen_at);

CREATE TABLE IF NOT EXISTS video (
    bvid        TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    up_name     TEXT,
    cover_url   TEXT,
    duration    INTEGER,
    pubdate     INTEGER,
    category    TEXT NOT NULL
                CHECK (category IN ('tech','life','humor','knowledge','emotion','entertainment')),
    strength    REAL NOT NULL CHECK (strength BETWEEN 0 AND 1),
    summary     TEXT NOT NULL CHECK (length(summary) <= 60),
    subtitle_head TEXT,
    ingested_at INTEGER NOT NULL,
    pushed_at   INTEGER,
    push_count  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_video_unpushed ON video(pushed_at, strength DESC);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


class BiliDB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- candidate ----------
    def seen(self, bvid: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM candidate WHERE bvid=?", (bvid,)
        ).fetchone() is not None

    def candidate(self, bvid: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM candidate WHERE bvid=?", (bvid,)
        ).fetchone()
        return dict(row) if row else None

    def add_candidate(self, bvid: str, title: str = "", up_name: str = "",
                      view: int = 0, pubdate: int = 0) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO candidate(bvid, first_seen_at, title, up_name, view, pubdate)"
            " VALUES (?,?,?,?,?,?)",
            (bvid, int(time.time()), title, up_name, view, pubdate),
        )
        self.conn.commit()

    def decide(self, bvid: str, decision: str, reason: str = "") -> None:
        self.conn.execute(
            "UPDATE candidate SET decision=?, reason=?, judged_at=? WHERE bvid=?",
            (decision, reason[:300], int(time.time()), bvid),
        )
        self.conn.commit()

    # ---------- video ----------
    def add_video(self, **kw) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO video(bvid,title,up_name,cover_url,duration,pubdate,"
                "category,strength,summary,subtitle_head,ingested_at)"
                " VALUES (:bvid,:title,:up_name,:cover_url,:duration,:pubdate,"
                ":category,:strength,:summary,:subtitle_head,:ingested_at)",
                kw,
            )
            self.conn.commit()
            return True
        except sqlite3.Error:
            self.conn.rollback()
            return False

    def count_today(self) -> int:
        start = int(time.time()) - 86400
        return self.conn.execute(
            "SELECT COUNT(*) FROM video WHERE ingested_at >= ?", (start,)
        ).fetchone()[0]

    def stats(self) -> dict:
        c = self.conn
        return {
            "candidates": c.execute("SELECT COUNT(*) FROM candidate").fetchone()[0],
            "videos": c.execute("SELECT COUNT(*) FROM video").fetchone()[0],
            "today": self.count_today(),
            "latest": [dict(r) for r in c.execute(
                "SELECT bvid,title,category,strength,summary FROM video"
                " ORDER BY ingested_at DESC LIMIT 5")],
        }

    # ---------- meta ----------
    def get_meta(self, k: str, default: str = "") -> str:
        row = self.conn.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return row[0] if row else default

    def set_meta(self, k: str, v: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (k, v),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
