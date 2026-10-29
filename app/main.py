"""FastAPI Web 应用：岗位列表筛选 + 统计面板。"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import settings
from db import repository
from db.database import now_str

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="秋招雷达", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

CATEGORY_LABELS = {"central": "央国企", "private": "民企", "foreign": "外企",
                   "unknown": "未分类"}
TYPE_LABELS = {"campus": "校招", "social": "社招"}


@app.get("/health")
def health():
    """探活端点：部署平台健康检查与快速验证用。"""
    stats = repository.count_jobs()
    total = repository.count_jobs(include_stale=True)["total"]
    return {"status": "ok", "jobs": stats["total"], "jobs_total": total,
            "today": stats["today"],
            "last_run": (stats.get("last_run") or {}).get("status")}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, category: str = "", recruit_type: str = "",
          keyword: str = "", include_stale: bool = False, open_only: bool = False,
          sort: str = "recent", page: int = 1):
    if sort not in ("recent", "deadline"):
        sort = "recent"
    page_size = 20
    rows, total = repository.list_jobs(category or None, recruit_type or None,
                                       keyword or None, include_stale=include_stale,
                                       open_only=open_only, sort=sort,
                                       limit=page_size, offset=(page - 1) * page_size)
    stats = repository.count_jobs(include_stale=include_stale, open_only=open_only)
    rows = [dict(j) | {"category_label": CATEGORY_LABELS.get(j["category"], "未知"),
                       "type_label": TYPE_LABELS.get(j["recruit_type"], "未知")}
            for j in rows]
    pages = max(1, (total + page_size - 1) // page_size)
    return templates.TemplateResponse(request, "index.html", {
        "jobs": rows, "stats": stats, "page": page, "pages": pages, "total": total,
        "category": category, "recruit_type": recruit_type, "keyword": keyword,
        "include_stale": include_stale, "open_only": open_only, "sort": sort,
        "max_age_days": settings.job_max_age_days, "today": now_str()[:10],
        "category_labels": CATEGORY_LABELS, "type_labels": TYPE_LABELS,
    })
