"""jobs / companies / crawl_runs 的读写操作。"""
import hashlib
import sqlite3

from db.database import get_conn, utcnow


def _norm(v: str | None) -> str:
    return (v or "").strip().lower()


def make_hash(company: str, title: str, location: str, apply_url: str) -> str:
    raw = f"{_norm(company)}|{_norm(title)}|{_norm(location)}|{_norm(apply_url).split('?')[0]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def upsert_company(conn: sqlite3.Connection, name: str, category: str | None,
                   category_source: str, confidence: float = 0.0) -> None:
    now = utcnow()
    conn.execute(
        """INSERT INTO companies (name, category, category_source, confidence, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(name) DO UPDATE SET
             category = COALESCE(excluded.category, category),
             category_source = excluded.category_source,
             confidence = excluded.confidence,
             updated_at = excluded.updated_at""",
        (name.strip(), category, category_source, confidence, now, now),
    )


def get_company_category(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute("SELECT category FROM companies WHERE name = ?", (_norm(name),)).fetchone()
    return row["category"] if row else None


def find_job_by_hash(conn: sqlite3.Connection, h: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM jobs WHERE content_hash = ?", (h,)).fetchone()


def insert_job(conn: sqlite3.Connection, job: dict) -> int:
    now = utcnow()
    cur = conn.execute(
        """INSERT INTO jobs (company_name, title, recruit_type, category, requirements,
                             location, apply_url, source, source_url, content_hash,
                             first_seen, last_seen)
           VALUES (:company_name, :title, :recruit_type, :category, :requirements,
                   :location, :apply_url, :source, :source_url, :content_hash, :now, :now)""",
        {**job, "now": now},
    )
    return cur.lastrowid


def touch_job(conn: sqlite3.Connection, job_id: int, updates: dict) -> None:
    """同一岗位再次出现时刷新 last_seen，并补充此前缺失的字段。"""
    sets, params = ["last_seen = ?"], [utcnow()]
    for col in ("requirements", "location", "apply_url", "recruit_type", "category"):
        if updates.get(col):
            sets.append(f"{col} = COALESCE({col}, ?)")
            params.append(updates[col])
    params.append(job_id)
    conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", params)


def start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO crawl_runs (started_at) VALUES (?)", (utcnow(),))
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, status: str, stats: dict) -> None:
    conn.execute(
        """UPDATE crawl_runs SET finished_at = ?, status = ?, total_raw = ?, new_jobs = ?,
               updated_jobs = ?, duplicates = ?, errors = ?, detail = ? WHERE id = ?""",
        (utcnow(), status, stats.get("total_raw", 0), stats.get("new_jobs", 0),
         stats.get("updated_jobs", 0), stats.get("duplicates", 0), stats.get("errors", 0),
         stats.get("detail", ""), run_id),
    )


def save_raw_items(conn: sqlite3.Connection, run_id: int, items: list[dict]) -> None:
    now = utcnow()
    conn.executemany(
        """INSERT INTO raw_items (run_id, source, url, raw_text, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        [(run_id, it["source"], it.get("url"), it.get("raw_text"), now) for it in items],
    )


def list_jobs(category: str | None, recruit_type: str | None, keyword: str | None,
              limit: int = 100, offset: int = 0) -> list[sqlite3.Row]:
    sql = "SELECT * FROM jobs WHERE 1=1"
    params: list = []
    if category:
        sql += " AND category = ?"
        params.append(category)
    if recruit_type:
        sql += " AND recruit_type = ?"
        params.append(recruit_type)
    if keyword:
        sql += " AND (title LIKE ? OR company_name LIKE ? OR requirements LIKE ?)"
        kw = f"%{keyword}%"
        params += [kw, kw, kw]
    sql += " ORDER BY last_seen DESC, id DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def count_jobs() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]
        by_cat = {r["category"] or "unknown": r["c"] for r in
                  conn.execute("SELECT category, COUNT(*) c FROM jobs GROUP BY category")}
        by_type = {r["recruit_type"] or "unknown": r["c"] for r in
                   conn.execute("SELECT recruit_type, COUNT(*) c FROM jobs GROUP BY recruit_type")}
        today = conn.execute(
            "SELECT COUNT(*) c FROM jobs WHERE substr(last_seen, 1, 10) = ?",
            (utcnow()[:10],),
        ).fetchone()["c"]
        last_run = conn.execute(
            "SELECT * FROM crawl_runs WHERE status != 'running' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {"total": total, "by_category": by_cat, "by_recruit_type": by_type,
                "today": today, "last_run": dict(last_run) if last_run else None}
