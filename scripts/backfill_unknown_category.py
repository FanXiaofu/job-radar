"""把来源先验兜底的分类回填为 unknown（未分类）。

默认 dry-run，只统计；确认后加 --apply 写入。脚本可重复执行。

用法：
    python scripts/backfill_unknown_category.py
    python scripts/backfill_unknown_category.py --apply
    python scripts/backfill_unknown_category.py --db data/job.db --apply
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings  # noqa: E402
from db.database import now_str  # noqa: E402


def backfill(conn: sqlite3.Connection, apply: bool = False) -> dict:
    """把 category_source='default' 的企业及其岗位改为 unknown。

    只处理来源先验兜底的行；名录（list）和 LLM 结果保持不变。
    返回本次影响的企业数与岗位数（dry-run 时为待处理数）。
    """
    companies = conn.execute(
        """SELECT COUNT(*) c FROM companies
           WHERE category_source = 'default'
             AND COALESCE(category, '') != 'unknown'"""
    ).fetchone()["c"]
    jobs = conn.execute(
        """SELECT COUNT(*) c FROM jobs
           WHERE COALESCE(category, '') != 'unknown'
             AND company_name IN (
                 SELECT name FROM companies WHERE category_source = 'default')"""
    ).fetchone()["c"]

    if apply and (companies or jobs):
        conn.execute(
            """UPDATE companies SET category = 'unknown', updated_at = ?
               WHERE category_source = 'default'
                 AND COALESCE(category, '') != 'unknown'""",
            (now_str(),),
        )
        conn.execute(
            """UPDATE jobs SET category = 'unknown'
               WHERE COALESCE(category, '') != 'unknown'
                 AND company_name IN (
                     SELECT name FROM companies WHERE category_source = 'default')"""
        )
        conn.commit()
    return {"companies": companies, "jobs": jobs}


def main() -> None:
    parser = argparse.ArgumentParser(description="把来源先验分类回填为未分类")
    parser.add_argument("--db", default=str(settings.db_path), help="SQLite 路径")
    parser.add_argument("--apply", action="store_true", help="实际写入；默认只统计")
    args = parser.parse_args()

    path = Path(args.db)
    if not path.exists():
        raise SystemExit(f"数据库不存在: {path}")

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        result = backfill(conn, apply=args.apply)
    finally:
        conn.close()

    mode = "已写入" if args.apply else "dry-run，未写入"
    print(f"{mode}：companies={result['companies']}，jobs={result['jobs']}（db={path}）")
    if not args.apply:
        print("确认后加 --apply 执行。")


if __name__ == "__main__":
    main()
