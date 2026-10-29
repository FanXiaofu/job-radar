"""从已有 requirements 文本中回填 deadline（报名/投递截止日期）。

默认 dry-run，只统计；确认后加 --apply 写入。脚本可重复执行。
只处理 deadline 为空的行，已有值不覆盖。

用法：
    python scripts/backfill_deadline.py
    python scripts/backfill_deadline.py --apply
    python scripts/backfill_deadline.py --db data/job.db --apply
"""
import argparse
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings  # noqa: E402
from db.database import init_db  # noqa: E402

DEADLINE_RE = re.compile(r"(?:报名截止|投递截止)\s*(\d{4}-\d{2}-\d{2})")
CLEAN_DEADLINE_RE = re.compile(r"[（(]?\s*(?:报名截止|投递截止)\s*\d{4}-\d{2}-\d{2}\s*[）)]?")
MAX_DEADLINE = (datetime.now() + timedelta(days=365 * 5)).strftime("%Y-%m-%d")


def backfill(conn: sqlite3.Connection, apply: bool = False) -> dict:
    # 先清理 2126 这类“长期有效”哨兵值，避免页面上出现百年后的截止日期。
    # 同时从 requirements 文本里清理，防止旧文本继续显示 2126。
    far_future: dict[int, str] = {}
    for row in conn.execute("SELECT id, requirements FROM jobs WHERE deadline > ?", (MAX_DEADLINE,)):
        far_future[row["id"]] = row["requirements"] or ""
    for row in conn.execute("SELECT id, requirements FROM jobs WHERE requirements LIKE '%截止%'"):
        match = DEADLINE_RE.search(row["requirements"] or "")
        if match and match.group(1) > MAX_DEADLINE:
            far_future[row["id"]] = row["requirements"] or ""

    rows = conn.execute(
        "SELECT id, requirements FROM jobs WHERE COALESCE(deadline, '') = ''"
    ).fetchall()
    updates = []
    for row in rows:
        match = DEADLINE_RE.search(row["requirements"] or "")
        if match and match.group(1) <= MAX_DEADLINE:
            updates.append((match.group(1), row["id"]))

    if apply:
        for job_id, requirements in far_future.items():
            cleaned = CLEAN_DEADLINE_RE.sub("", requirements)
            cleaned = re.sub(r"；\s*；", "；", cleaned).strip("； ")
            conn.execute(
                "UPDATE jobs SET deadline = '', requirements = ? WHERE id = ?",
                (cleaned, job_id),
            )
        if updates:
            conn.executemany("UPDATE jobs SET deadline = ? WHERE id = ?", updates)
        conn.commit()
    return {"jobs": len(updates), "cleared": len(far_future)}


def main() -> None:
    parser = argparse.ArgumentParser(description="从 requirements 文本回填 deadline")
    parser.add_argument("--db", default=str(settings.db_path), help="SQLite 路径")
    parser.add_argument("--apply", action="store_true", help="实际写入；默认只统计")
    args = parser.parse_args()

    path = Path(args.db)
    if not path.exists():
        raise SystemExit(f"数据库不存在: {path}")

    settings.db_path = path.resolve()
    init_db()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        result = backfill(conn, apply=args.apply)
    finally:
        conn.close()

    mode = "已写入" if args.apply else "dry-run，未写入"
    print(f"{mode}：jobs={result['jobs']}，cleared={result['cleared']}（db={path}）")
    if not args.apply:
        print("确认后加 --apply 执行。")


if __name__ == "__main__":
    main()
