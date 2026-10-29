"""用当前名录/LLM 重新分类企业，并把新分类同步到 jobs。

默认 dry-run，只统计；确认后加 --apply 写入。可重复执行。

用法：
    python scripts/reclassify_companies.py
    python scripts/reclassify_companies.py --apply
    python scripts/reclassify_companies.py --db data/job.db --apply
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.classifier import CompanyClassifier  # noqa: E402
from config import settings  # noqa: E402
from db.database import now_str  # noqa: E402


def reclassify(conn: sqlite3.Connection, apply: bool = False) -> dict:
    """只采用名录/LLM 的高置信度结果；未命中保持原状。"""
    classifier = CompanyClassifier()
    rows = conn.execute(
        "SELECT name, category, category_source FROM companies ORDER BY name"
    ).fetchall()

    changes = []
    for row in rows:
        category, source, confidence = classifier.classify(row["name"])
        if source not in ("list", "llm"):
            continue
        if category == row["category"] and source == row["category_source"]:
            continue
        changes.append({
            "name": row["name"],
            "old_category": row["category"],
            "old_source": row["category_source"],
            "category": category,
            "source": source,
            "confidence": confidence,
        })

    jobs = 0
    for change in changes:
        jobs += conn.execute(
            """SELECT COUNT(*) c FROM jobs
               WHERE company_name = ? AND COALESCE(category, '') != ?""",
            (change["name"], change["category"]),
        ).fetchone()["c"]

    if apply and changes:
        now = now_str()
        for change in changes:
            conn.execute(
                """UPDATE jobs SET category = ?
                   WHERE company_name = ? AND COALESCE(category, '') != ?""",
                (change["category"], change["name"], change["category"]),
            )
            conn.execute(
                """UPDATE companies
                   SET category = ?, category_source = ?, confidence = ?, updated_at = ?
                   WHERE name = ?""",
                (change["category"], change["source"], change["confidence"],
                 now, change["name"]),
            )
        conn.commit()

    return {"companies": len(changes), "jobs": jobs, "changes": changes}


def main() -> None:
    parser = argparse.ArgumentParser(description="用名录/LLM 重新分类企业")
    parser.add_argument("--db", default=str(settings.db_path), help="SQLite 路径")
    parser.add_argument("--apply", action="store_true", help="实际写入；默认只统计")
    args = parser.parse_args()

    path = Path(args.db)
    if not path.exists():
        raise SystemExit(f"数据库不存在: {path}")

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        result = reclassify(conn, apply=args.apply)
    finally:
        conn.close()

    mode = "已写入" if args.apply else "dry-run，未写入"
    print(f"{mode}：companies={result['companies']}，jobs={result['jobs']}（db={path}）")
    for change in result["changes"][:20]:
        print(f"  {change['name']}: {change['old_category']} -> "
              f"{change['category']} ({change['source']}, {change['confidence']})")
    if len(result["changes"]) > 20:
        print(f"  ... 其余 {len(result['changes']) - 20} 条省略")
    if not args.apply:
        print("确认后加 --apply 执行。")


if __name__ == "__main__":
    main()
