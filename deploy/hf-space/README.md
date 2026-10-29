---
title: 秋招雷达 JobRadar
emoji: 🎯
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: 每天自动采集国聘/牛客秋招岗位，按企业性质、招聘类型和关键词筛选
---

# 秋招雷达 JobRadar

秋招岗位信息分散在国聘、牛客等渠道，逐一查看筛选费时。本项目每天定时采集岗位，结构化入库，按 **企业性质（央国企/民企/外企/未分类）× 招聘类型（校招/社招）× 关键词** 筛选，并尽量提供投递入口。

- 数据来源：国聘、牛客公开接口，仅供求职参考，投递以企业官方页面为准
- 采集频率：每天 09:00（Asia/Shanghai）；单轮约 2 分钟
- 免费 Space 重建后 SQLite 会丢失，应用启动时会自动重新采集，首轮约 2 分钟
- LLM 抽取/分类默认关闭；未命中名录的企业标记为“未分类”，不按来源平台猜测
- 默认只展示近 30 天有更新的岗位，可勾选查看历史岗位
- 源码：https://github.com/FanXiaofu/job-radar

仅供学习与个人求职使用。
