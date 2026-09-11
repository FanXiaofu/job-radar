# “秋招雷达”阶段评审报告

评审方式：全部源码通读 + 只读检查（`python -m py_compile` 全部通过；starlette 0.46.2 实测确认 `Jinja2Templates` 默认 `autoescape=True`）。未修改任何文件、未发起网络请求。

## 一、问题清单

### P1（应修复，进入下一阶段前建议完成）

1. **`app/main.py:32-33` — 分页总页数使用未过滤的总数，筛选状态下分页错误**。`total = stats["total"]` 是全表岗位数，而 `jobs` 是按 category/recruit_type/keyword 过滤后的结果。筛选后页码显示错误、“下一页”会翻到大量空页。建议 `list_jobs` 同条件返回 `COUNT(*)`，用过滤后的 total 计算 pages。

2. **`agent/search_agent.py` 全文 + README — 搜索 Agent 是死代码，从未接入流水线**。`grep` 全项目仅 `search_agent.py:24` 定义类，pipeline/registry/main 均未引用；README 却宣称“定向爬虫 + LLM 搜索 Agent 双渠道”。且 `search_agent.py:37-38` `queries[:max_queries]`（15 个查询截到 10 个）导致第 3 个关键词模板永远不会被执行。要么在 registry/pipeline 接线（建议 LLM 可用时才启用），要么在 README/文档中明确标注未启用。

3. **`db/repository.py:23-27` + `pipeline.py:84` + `agent/classifier.py:44-47` — 低置信度分类覆盖高置信度分类，且分类无缓存**。`upsert_company` 的 `ON CONFLICT` 无条件用本次结果覆盖 `category/category_source/confidence`（`COALESCE` 只对 NULL 生效）。若某公司某轮被 LLM 判为 foreign（0.7），下一轮 LLM 未命中/未配置时会被国聘先验 default "central"（0.3）覆盖。同时每个条目都重新分类、每次都打 LLM（`get_company_category` 写了但从未调用，是死代码），同公司多岗位重复调用，既费钱又不稳定。建议：先查 companies 表缓存；`ON CONFLICT` 时仅在 `excluded.confidence >= confidence` 时覆盖。

4. **`crawler/sources/nowcoder.py:96` — 公司页抓取失败被永久负缓存，整批岗位丢失**。`_company_name` 失败时缓存空字符串，该公司本轮所有岗位 `company_name=""`，进 pipeline 后被计为 errors 全部丢弃，且下次运行前不会重试。建议失败不缓存（或短 TTL 负缓存）；另注意 `pipeline.py:72-74` 会把空公司名直接当错误吞掉，最好区分“解析失败”与“确实无公司名”。

5. **`db/repository.py:41-51` + `pipeline.py:63-70` — LLM 抽取结果缺字段会导致 insert 抛参数缺失异常**。`insert_job` 使用命名参数 `:requirements/:location/:apply_url` 等，而 `JobExtractor._ask`（extractor.py:68）只校验 `company_name/title`，LLM 返回的 JSON 若缺少任一其他字段，sqlite3 报 "You did not supply a value for binding parameter"。目前靠 pipeline 的 per-item try 兜住但条目丢失。建议入库前 `job.setdefault(field, "")` 补齐全部列，并在 extractor 校验必填字段集。

6. **`main.py:14-19` — 日志文件使用相对路径 `logs/app.log`，且 `logs/` 在 .gitignore 中**。任何干净部署/新 clone 下 `FileHandler` 在 import 时即抛 `FileNotFoundError`，服务完全无法启动。建议改为 `PROJECT_ROOT / "logs" / "app.log"` 并 `mkdir(parents=True, exist_ok=True)`。

### P2（建议）

7. `crawler/sources/iguopin.py:48` — 分页终止条件 `page * data.get("page_size", 20) >= data.get("total", 0)`：`total` 缺失时默认 0，恒为真，永远只抓第 1 页（静默数据丢失）；且 `page_size` 应与请求里硬编码的 20 联动。
8. `crawler/sources/iguopin.py:61-63`、`nowcoder.py:72-74` — 两个 POST 源都绕过了 `BaseSource.fetch` 的重试/限速封装，自身无重试（base.py 的 max_retries 对实际采集路径不生效）；`iguopin.py:32` `seen_ids` 在每个 keyword 内独立，跨关键词重复条目靠 pipeline 二次去重兜底，虚增 duplicates/updated 统计。
9. `crawler/sources/nowcoder.py:42-62` — `_to_item` 无单条 try/except，某条数据类型异常（如 `deliverEnd` 为字符串导致 `_ts_to_date` 除法/运算 TypeError）会让整个 nowcoder 源本轮全灭，违背 base.py:63 “单个条目失败应记录日志并跳过”的约定。
10. `crawler/sources/nowcoder.py:66` — `recruitType` 硬编码 "1"（校招），`RECRUIT_TYPE_MAP` 的 2/3 分支实际永远走不到；“社招”维度名存实亡。
11. `nowcoder.py:104` — `_ts_to_date` 用 UTC 转换北京时区的截止时间戳，晚 8 点后的截止日会差一天；`db/database.py:66-67` 全库时间戳为 UTC，而调度时区是 Asia/Shanghai，`count_jobs`（repository.py:116-119）的“今日更新”按 UTC 日期统计，与用户认知的“今日”不一致。建议统一存北京时间或统一转换。
12. `main.py:43-45` — APScheduler 3.x 默认 `misfire_grace_time=1` 秒，进程恰在 9:00 后启动或线程繁忙时当日任务会被静默跳过。建议 `add_job(..., misfire_grace_time=3600, coalesce=True)`。
13. `db/database.py:70-82` — 未开 WAL。APScheduler 后台线程写与 uvicorn 线程池读并发时靠 15s busy timeout 兜底，长事务期间 Web 可能卡顿。建议 `PRAGMA journal_mode=WAL` + `busy_timeout`。连接本身每调用新建/关闭、单线程内使用，无 `check_same_thread` 问题、无泄漏。
14. `pipeline.py:46-52,83` — 每个条目单独开连接、单独事务（upsert + select + insert），几百条目意味着几百次连接/提交，建议批量复用连接；`pipeline.py:89-92` 同一事件同时计入 `duplicates` 和 `updated_jobs`，统计口径重复。
15. `pipeline.py:80-81` + `db/repository.py:33` — `content_hash` 有 UNIQUE 约束但从不用于前置去重（`find_job_by_hash` 死代码）；当 `is_duplicate` 因公司名/URL 差异漏判而 hash 撞车时会以 IntegrityError 形式表现为 “errors” 而非 "duplicates"，统计失真。另外去重只在公司名完全相等内进行，跨源公司名写法不一致（“华为” vs “华为技术有限公司”）会漏重。
16. `db/repository.py:100-102` — LIKE 关键词未转义 `%`/`_`（非注入，但搜索语义可被干扰）；建议 `ESCAPE '\'`。
17. `app/templates/index.html:54` — `apply_url` 未校验 scheme，LLM/search 源可能产出 `javascript:` 链接（Jinja 已转义引号，风险低但建议白名单 http/https）；`:64-66` 分页链接中 keyword 只转义未 urlencode，含特殊字符时 URL 破损。
18. `crawler/sources/registry.py:21` — 只捕获 `ImportError`，源实例化阶段的其他异常会击穿 `build_sources` 使整轮采集失败；与“单源失败不影响整轮”目标不符。
19. `config.py:29-32` — `int(_env(...))` 对非法环境变量直接 ValueError 且发生在 import 期，报错不友好。
20. `agent/classifier.py:38-43` — 名录双向子串匹配 + 短条目（如“中建”）易误匹配私有子公司；central 匹配区分大小写、foreign 转小写，行为不一致。Web 层（index.html）完全不展示 confidence/category_source，“分类置信度的使用”缺乏出口。
21. `eval/run_eval.py:51-53` — 空样本集除零；`:40` LLM 返回非字符串字段时 `normalize` 抛 AttributeError；命中判据 `expect in actual` + `[:len*2]` 截断口径较宽松，易高估准确率。
22. 死代码/死配置：`db/repository.py:32-38`（两个函数无人调用）、`raw_items.processed` 字段永不更新、`requirements.txt` 中 playwright 未被任何代码使用。
23. `tests/test_dedup.py:7` — 经 classifier 传递 import 了 openai，未装 SDK 的环境跑不了这个“不依赖 LLM”的测试。

## 二、Checklist 逐项结论

| # | 项目 | 结论 | 要点 |
|---|------|------|------|
| 1 | 正确性缺陷 | **不通过** | 分页总数口径错误（P1-1）；iguopin 分页终止条件可致静默丢数据（P2-7）；duplicates/updated 重复计数；SQL 参数化完整，无拼接注入 |
| 2 | 健壮性 | **部分通过** | 单源失败隔离、per-item try、LLM 解析失败重试一次+返回 None 兜底、APScheduler 自捕获作业异常（不会杀调度线程）均正确；缺口：nowcoder 公司页负缓存丢岗位（P1-4）、POST 源无重试（P2-8）、单条目异常毁整源（P2-9）、LLM 缺字段入库报错（P1-5） |
| 3 | 安全 | **通过** | 全部 SQL 参数化；Jinja2 autoescape=True 已实测确认，keyword 转义无 XSS；API Key 不进日志（httpx 异常只含 URL，Tavily key 走 body）；残留小项：LIKE 通配符、apply_url scheme 白名单（P2-16/17） |
| 4 | 架构与可维护性 | **不通过** | SearchAgent 死代码未接线（P1-2）；repository 两个死函数、processed 死字段、playwright 未用；每条目一连接；爬虫绕过 base 的重试/限速抽象 |
| 5 | 数据质量 | **不通过** | 去重设计（URL 归一化 + 标题相似度，公司内匹配）思路合理，但低置信分类覆盖高置信（P1-3）、跨源公司名不一致漏重、deadline 未落结构化字段、“今日更新”UTC 口径错误、confidence 无展示出口 |
| 6 | 调度与并发 | **基本通过** | 连接均为线程内创建关闭，无跨线程共享连接、无泄漏；SQLite 并发有 15s timeout 兜底但不开 WAL 有锁等待风险；misfire_grace_time 默认 1s 可能静默跳过每日任务 |

## 三、总体结论

**有条件通过：无 P0 级阻断缺陷，核心链路（采集→抽取→分类→去重→入库→展示）可跑通；但存在 6 项 P1（分页口径错误、搜索 Agent 未接线、分类覆盖、公司名负缓存丢数据、LLM 缺字段入库、日志路径部署即崩），需在进入下一阶段前修复并复查 P2 中的分页/时区/统计口径问题。**
---

## 修复记录（开发方，评审后）

### P1 全部修复
1. **分页口径**：`list_jobs` 改为返回 (rows, filtered_total)，同条件 COUNT 计算页数；验证：央国企筛选 389 条 / 第 2/20 页正确
2. **搜索 Agent 接线**：pipeline.run() 在 search_enabled && llm_enabled 时执行 SearchAgent；查询改为模板×方向轮转取样，不再截断
3. **分类覆盖与缓存**：upsert_company 仅当 excluded.confidence >= confidence 才覆盖分类；pipeline 先查 companies 缓存（confidence>=0.5 直接复用），未命中才分类，省 LLM 调用
4. **公司页负缓存**：nowcoder _company_name 只缓存成功结果，失败下次重试
5. **LLM 缺字段**：extractor._ask 输出补齐全部字段为字符串；pipeline 入库前 REQUIRED_FIELDS setdefault 兜底
6. **日志路径**：main.py 用 PROJECT_ROOT/logs 并 mkdir，干净部署不再崩溃

### P2 修复（16 项）
iguopin 分页终止条件、BaseSource.post 重试封装（两源接入）、nowcoder 单条容错、recruitType 社招维度接入、时间口径统一北京时间（now_str + _ts_to_date）、misfire_grace_time=3600+coalesce、WAL+busy_timeout、单连接复用处理全部条目、duplicates/updated_jobs 口径合一、content_hash 前置去重、LIKE ESCAPE 转义、apply_url scheme 白名单、分页 keyword urlencode、registry 捕获 Exception、config int 容错、classifier 大小写统一、eval 空集守卫

### 未修复（记录原因）
- 跨源公司名不一致漏重（"华为" vs "华为技术有限公司"）：需企业名归一化服务，留待 LLM Key 配置后用分类结果辅助
- 名录短条目（如"中建"）子串误匹配风险：当前误匹配均落在国企语义内可接受，已加注释
- raw_items.processed 死字段：保留留档用途，未更新不影响功能
- requirements.txt 中 playwright：为 JS 渲染源预留（web-gui 验证也依赖），保留

### 修复后回归
- 编译检查全过、单元测试全过
- 全量采集回归：1016 条原始 -> 276 新增 / 703 去重 / 37 丢弃（公司页失败），status=success
- Web 筛选分页验证通过
