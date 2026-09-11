# 秋招雷达 JobRadar

每天 9:00 自动运行的秋招信息聚合平台：多渠道采集 → LLM 结构化抽取 → 企业分类 → 去重入库 → Web 展示。

> 数据来自公开渠道，仅供参考，投递请以企业官方页面为准。

## 功能

- **自主采集**：定向爬虫（国聘网等）+ LLM 搜索 Agent 双渠道，每天定时更新
- **三维信息**：企业类型（央国企/民企/外企）、招聘类型（社招/校招）、岗位详情（要求/地点/投递链接）
- **AI 处理**：LLM 结构化抽取（JSON Schema 约束 + 失败重试）、名录优先的企业分类（带置信度）、URL+标题双层去重
- **Web 界面**：分类筛选、关键词搜索、统计面板、投递链接直达

## 架构

```
┌──────────────────────────── 采集层 crawler/ ───────────────────────────┐
│  国聘网 adapter     牛客网 adapter     搜索 Agent（博查/Tavily）       │
│         └─────────────── RawItem（原始条目留档 raw_items）─────────────┘
┌──────────────────────────── AI 层 agent/ ──────────────────────────────┐
│  JobExtractor        CompanyClassifier         dedup                  │
│  LLM→JSON Schema     央企名录+外企名录→LLM兜底    URL归一化+标题相似度    │
└──────────────────────────────┬────────────────────────────────────────┘
                        Pipeline（流水线编排，crawl_runs 记录每次运行）
                               ↓
                    SQLite（companies / jobs / raw_items / crawl_runs）
                               ↓
                FastAPI Web（筛选 / 搜索 / 统计面板）+ APScheduler 定时
```

## 快速开始

```bash
# 1. 安装依赖（Python 3.11+）
pip install -r requirements.txt
# 如需 JS 渲染的源：playwright install chromium

# 2. 配置
cp .env.example .env   # 填入 LLM_API_KEY（推荐 DeepSeek）；搜索 API 可选

# 3. 立即采集一轮
python main.py crawl

# 4. 启动 Web（含每天 09:00 定时采集）
python main.py serve    # 访问 http://127.0.0.1:8000
```

## 配置说明（.env）

| 变量 | 说明 | 默认 |
|---|---|---|
| LLM_API_KEY / LLM_BASE_URL / LLM_MODEL | OpenAI 兼容接口 | DeepSeek |
| SEARCH_PROVIDER / SEARCH_API_KEY | bocha / tavily / none | none |
| SCHEDULE_HOUR / SCHEDULE_MINUTE | 定时采集时刻 | 9:00 |
| DB_PATH | SQLite 路径 | data/job.db |

## 质量保障与实测指标

### 实测运行数据（2026-09 开发期，连续 4 轮真实采集）

| 指标 | 数值 | 说明 |
|---|---|---|
| 岗位入库总数 | **1021** | 央国企 389 / 民企 622 / 外企 10，校招 610 / 社招 411 |
| 累计采集原始条目 | 3347 | 两个结构化源 × 6-14 组关键词 |
| 去重识别率 | **58.5%** | 1438/2459 条重复被正确识别并刷新，未重复入库 |
| 覆盖企业数 | 423 | 含名录精确匹配 24 家（置信度 1.0），其余先验兜底 |
| 单轮采集耗时 | ~4 分钟 | 含限速（1.5s/请求）、公司页解析与全部重试 |

> LLM 抽取准确率：`eval/golden_samples.jsonl` 15 条人工标注样本，配置 Key 后运行 `python eval/run_eval.py` 输出字段级准确率。结构化 API 源不走 LLM，字段准确率取决于源接口。

### 工程质量机制

- **独立 AI 评审**：每个阶段由全新上下文的 AI 评审员按六项 checklist（正确性/健壮性/安全/架构/数据质量/并发）审查，首轮评审发现 6 项 P1 + 17 项 P2，全部修复并回归（报告见 `docs/reviews/01-阶段评审-爬虫流水线Web.md`）
- **单元测试**：`python tests/test_dedup.py`（去重、名录分类，不依赖网络与 Key）
- **运行留痕**：`crawl_runs` 记录每轮采集的新增/去重/丢弃数，`raw_items` 保留原始数据可回溯

## 已知边界

- 牛客"校招日程全量分页"接口需登录，当前仅采集匿名可读的职位搜索接口
- 跨源企业名不一致（"华为" vs "华为技术有限公司"）暂不合并，配置 LLM Key 后可借助分类结果辅助归一
- 搜索 Agent 需要同时配置搜索 API Key 与 LLM Key，二者缺一则自动跳过

## 项目过程

开发计划、阶段评审与修复记录见 `docs/reviews/`。

## License

仅供学习与个人求职使用。
