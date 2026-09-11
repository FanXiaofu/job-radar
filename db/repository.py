"""jobs / companies / crawl_runs 的读写操作。"""
import hashlib
import sqlite3

from db.database import get_conn, now_str

JOB_COLUMNS = ("company_name", "title", "recruit_type", "category", "requirements",
               "location", "apply_url", "source", "source_url")


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
                             location, apply_url, source, source_url, content_hash,
                             first_seen, last_seen)
           VALUES (:company_name, :title, :recruit_type, :category, :requirements,
                   :location, :apply_url, :source, :source_url, :content_hash, :now, :now)""",
        {**job, "now": now},
    )
    return cur.lastrowid


def touch_job(conn: sqlite3.Connection, job_id: int, updates: dict) -> None:
    """同一岗位再次出现时刷新 last_seen，并补充此前缺失的字段。"""
    sets, params = ["last_seen = ?"], [now_str()]
    for col in ("requirements", "location", "apply_url", "recruit_type", "category"):
        if updates.get(col):
            sets.append(f"{col} = COALESCE({col}, ?)")
            params.append(updates[col])
    params.append(job_id)
    conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", params)


def start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO crawl_runs (started_at) VALUES (?)", (now_str(),))
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, status: str, stats: dict) -> None:
    conn.execute(
        """UPDATE crawl_runs SET finished_at = ?, status = ?, total_raw = ?, new_jobs = ?,
               updated_jobs = ?, duplicates = ?, errors = ?, detail = ? WHERE id = ?""",
        (now_str(), status, stats.get("total_raw", 0), stats.get("new_jobs", 0),
         stats.get("duplicates", 0), stats.get("duplicates", 0), stats.get("errors", 0),
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
              limit: int = 100, offset: int = 0) -> tuple[list[sqlite3.Row], int]:
    """返回 (岗位列表, 过滤后的总数)。总数用于正确分页。"""
    where, params = " WHERE 1=1", []
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
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) c FROM jobs{where}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM jobs{where} ORDER BY last_seen DESC, id DESC LIMIT ? OFFSET ?",
            params + [limit, offset]).fetchall()
    return rows, total


def count_jobs() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]
        by_cat = {r["category"] or "unknown": r["c"] for r in
                  conn.execute("SELECT category, COUNT(*) c FROM jobs GROUP BY category")}
        by_type = {r["recruit_type"] or "unknown": r["c"] for r in
                   conn.execute("SELECT recruit_type, COUNT(*) c FROM jobs GROUP BY recruit_type")}
        today = conn.execute(
            "SELECT COUNT(*) c FROM jobs WHERE substr(last_seen, 1, 10) = ?",
            (now_str()[:10],),
        ).fetchone()["c"]
        last_run = conn.execute(
            "SELECT * FROM crawl_runs WHERE status != 'running' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {"total": total, "by_category": by_cat, "by_recruit_type": by_type,
                "today": today, "last_run": dict(last_run) if last_run else None}
