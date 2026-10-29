"""jobs / companies / crawl_runs 的读写操作。"""
import hashlib
import sqlite3

from config import settings
from db.database import days_ago_str, get_conn, now_str


def _norm(v: str | None) -> str:
    return (v or "").strip().lower()


def make_hash(company: str, title: str, location: str, apply_url: str) -> str:
    raw = f"{_norm(company)}|{_norm(title)}|{_norm(location)}|{_norm(apply_url).split('?')[0]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def upsert_company(conn: sqlite3.Connection, name: str, category: str | None,
                   category_source: str, confidence: float = 0.0) -> None:
    """新增或更新企业分类。已有高置信度结果不被低置信度覆盖。"""
    now = now_str()
    conn.execute(
        """INSERT INTO companies (name, category, category_source, confidence, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(name) DO UPDATE SET
             category = CASE WHEN excluded.confidence >= confidence
                        THEN excluded.category ELSE category END,
             category_source = CASE WHEN excluded.confidence >= confidence
                               THEN excluded.category_source ELSE category_source END,
             confidence = MAX(confidence, excluded.confidence),
             updated_at = excluded.updated_at""",
        (name.strip(), category, category_source, confidence, now, now),
    )


def get_company_category(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    """查企业分类缓存，命中则跳过重复分类（省 LLM 调用且结果稳定）。"""
    return conn.execute(
        "SELECT category, confidence FROM companies WHERE name = ?",
        (name.strip(),),
    ).fetchone()


def find_job_by_hash(conn: sqlite3.Connection, h: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM jobs WHERE content_hash = ?", (h,)).fetchone()


def insert_job(conn: sqlite3.Connection, job: dict) -> int:
    now = now_str()
    cur = conn.execute(
        """INSERT INTO jobs (company_name, title, recruit_type, category, requirements,
                             location, deadline, apply_url, source, source_url, content_hash,
                             first_seen, last_seen)
           VALUES (:company_name, :title, :recruit_type, :category, :requirements,
                   :location, :deadline, :apply_url, :source, :source_url, :content_hash, :now, :now)""",
        {**job, "now": now, "deadline": job.get("deadline", "")},
    )
    return cur.lastrowid


def touch_job(conn: sqlite3.Connection, job_id: int, updates: dict) -> bool:
    """刷新 last_seen，并补齐此前为空的字段；返回是否补到了字段。"""
    row = conn.execute(
        "SELECT requirements, location, deadline, apply_url, recruit_type, category FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        return False
    sets, params = ["last_seen = ?"], [now_str()]
    changed = False
    for col in ("requirements", "location", "deadline", "apply_url", "recruit_type", "category"):
        if updates.get(col) and not (row[col] or "").strip():
            sets.append(f"{col} = ?")
            params.append(updates[col])
            changed = True
    params.append(job_id)
    conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", params)
    return changed


def start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO crawl_runs (started_at) VALUES (?)", (now_str(),))
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, status: str, stats: dict) -> None:
    conn.execute(
        """UPDATE crawl_runs SET finished_at = ?, status = ?, total_raw = ?, new_jobs = ?,
               updated_jobs = ?, duplicates = ?, errors = ?, detail = ? WHERE id = ?""",
        (now_str(), status, stats.get("total_raw", 0), stats.get("new_jobs", 0),
         stats.get("updated_jobs", 0), stats.get("duplicates", 0), stats.get("errors", 0),
         stats.get("detail", ""), run_id),
    )


def save_raw_items(conn: sqlite3.Connection, run_id: int, items: list[dict]) -> None:
    now = now_str()
    conn.executemany(
        """INSERT INTO raw_items (run_id, source, url, raw_text, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        [(run_id, it["source"], it.get("url"), it.get("raw_text"), now) for it in items],
    )


def _escape_like(keyword: str) -> str:
    return keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_jobs(category: str | None, recruit_type: str | None, keyword: str | None,
              include_stale: bool = False, open_only: bool = False, sort: str = "recent",
              max_age_days: int | None = None,
              limit: int = 100, offset: int = 0) -> tuple[list[sqlite3.Row], int]:
    """返回 (岗位列表, 过滤后的总数)。默认只统计最近 N 天有更新的岗位。"""
    days = settings.job_max_age_days if max_age_days is None else max_age_days
    where, params = " WHERE 1=1", []
    if not include_stale:
        where += " AND last_seen >= ?"
        params.append(days_ago_str(days))
    if open_only:
        where += " AND (deadline IS NULL OR deadline = '' OR deadline >= ?)"
        params.append(now_str()[:10])
    if category:
        where += " AND category = ?"
        params.append(category)
    if recruit_type:
        where += " AND recruit_type = ?"
        params.append(recruit_type)
    if keyword:
        where += r" AND (title LIKE ? ESCAPE '\' OR company_name LIKE ? ESCAPE '\' OR requirements LIKE ? ESCAPE '\')"
        kw = f"%{_escape_like(keyword)}%"
        params += [kw, kw, kw]
    order = ("ORDER BY (deadline IS NULL OR deadline = '') ASC, deadline ASC, "
             "last_seen DESC, id DESC"
             if sort == "deadline" else "ORDER BY last_seen DESC, id DESC")
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) c FROM jobs{where}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM jobs{where} {order} LIMIT ? OFFSET ?",
            params + [limit, offset]).fetchall()
    return rows, total


def count_jobs(include_stale: bool = False, open_only: bool = False,
               max_age_days: int | None = None) -> dict:
    days = settings.job_max_age_days if max_age_days is None else max_age_days
    conditions, params = [], []
    if not include_stale:
        conditions.append("last_seen >= ?")
        params.append(days_ago_str(days))
    if open_only:
        conditions.append("(deadline IS NULL OR deadline = '' OR deadline >= ?)")
        params.append(now_str()[:10])
    clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) c FROM jobs{clause}", params).fetchone()["c"]
        by_cat = {r["category"] or "unknown": r["c"] for r in
                  conn.execute(f"SELECT category, COUNT(*) c FROM jobs{clause} GROUP BY category", params)}
        by_type = {r["recruit_type"] or "unknown": r["c"] for r in
                   conn.execute(f"SELECT recruit_type, COUNT(*) c FROM jobs{clause} GROUP BY recruit_type", params)}
        today_conditions = ["substr(last_seen, 1, 10) = ?"]
        today_params = [now_str()[:10]]
        if not include_stale:
            today_conditions.append("last_seen >= ?")
            today_params.append(days_ago_str(days))
        if open_only:
            today_conditions.append("(deadline IS NULL OR deadline = '' OR deadline >= ?)")
            today_params.append(now_str()[:10])
        today_sql = f"SELECT COUNT(*) c FROM jobs WHERE {' AND '.join(today_conditions)}"
        today = conn.execute(today_sql, today_params).fetchone()["c"]
        last_run = conn.execute(
            "SELECT * FROM crawl_runs WHERE status != 'running' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {"total": total, "by_category": by_cat, "by_recruit_type": by_type,
                "today": today, "last_run": dict(last_run) if last_run else None}
