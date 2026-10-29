# 部署指南

四种方式，按场景选择：

| 方式 | 成本 | 适用场景 |
|---|---|---|
| Render Free Docker | 免费 | 公网演示，15 分钟无访问休眠；适合简历链接 |
| Hugging Face Spaces | 免费/付费 | 免费账号 Docker/Gradio 目前显示 Paid；免费只能 Static |
| 本机 + cpolar | 免费 | 面试当天演示，流畅稳定 |
| Docker Compose | 需一台服务器 | 有云服务器时的最佳方案 |

---

## 方式一：Render 免费 Docker（推荐）

1. 打开 <https://render.com/deploy?repo=https://github.com/FanXiaofu/job-radar>，用 GitHub 登录并授权。
2. Render 会读取仓库根目录的 `render.yaml`，创建 Free Web Service。确认：
   - Runtime：Docker
   - Plan：Free
   - Health Check Path：`/health`
   - 环境变量：`WEB_HOST=0.0.0.0`、`JOB_MAX_AGE_DAYS=30`
3. 可选：在 Environment 中添加 `LLM_API_KEY`（DeepSeek Key）；不加也能运行。
4. 点 Deploy；首次构建约 2–5 分钟，完成后地址形如 `https://job-radar-xxxx.onrender.com`。
5. 验证：`https://.../health` 返回 JSON，首页可访问。

免费限制（Render 官方）：

- 免费 Web Service 15 分钟无访问会休眠，下一次请求唤醒约 1 分钟。
- 本地 SQLite 在重启、休眠、重部署后丢失；应用检测到空库会自动重新采集（约 2 分钟）。
- 750 免费实例小时/月；免费实例不支持持久磁盘，适合演示，不适合生产。

---

## 方式二：Hugging Face Spaces（Docker/Gradio 当前为 Paid）

> 注意：截至 2026-10，HF 免费账号创建 Docker/Gradio Space 会显示 Paid；免费只能用 Static，Static 无法运行 FastAPI。若不想付费，请用 Render 或云服务器。

1. **注册** [huggingface.co](https://huggingface.co)（邮箱即可，免费）
2. 右上角头像 → New Space：
   - Space name：`job-radar`
   - SDK：选 **Docker**（Blank 模板）
   - Visibility：Public
3. 在本地准备最小部署目录（自动写入 HF Docker Space 的 README frontmatter，
   避免主仓库 README 覆盖 `sdk: docker` / `app_port: 7860`）：

   ```bash
   python scripts/prepare_hf_space.py --out _hf_space
   ```

4. **克隆刚创建的 Space 仓库，把 `_hf_space` 内容复制进去再推送**。
   Space 创建时会自带一个初始 README，直接 `git init + push` 会 non-fast-forward；
   clone 后覆盖最稳：

   ```bash
   git clone https://huggingface.co/spaces/<用户名>/job-radar
   cd job-radar
   # Windows PowerShell（robocopy 退出码 1 表示成功复制）：
   robocopy "<项目路径>\_hf_space" "." /E /XD .git
   # macOS / Linux：
   # rsync -a --exclude .git ../_hf_space/ .
   git add .
   git commit -m "deploy job-radar"
   git push
   ```

   推送时用户名填 HF 用户名，密码填 HF Access Token
   （头像 → Settings → Access Tokens → 新建，勾 write 权限）。`_hf_space` 只包含运行所需文件，
   不包含数据库、日志、测试和 `.env`。
5. **配置 Secret**（密钥不进代码库）：Space 页面 → Settings → Variables and secrets
   → New secret：`LLM_API_KEY` = 你的 DeepSeek Key
6. 等 Docker 自动构建（首次约 2~5 分钟），Build 日志在页面顶部可见
7. 验证：打开 Space URL，页面出现岗位列表即成功；`<Space URL>/health` 返回 JSON，
   Dockerfile 已带 `HEALTHCHECK`，页面状态会显示 healthy

**注意事项**：
- 免费版 Space 重建后 SQLite 数据丢失，应用启动时会检测空库自动重新采集（首轮约 2–5 分钟，随岗位数量变化），
  期间页面显示"暂无岗位数据"属正常
- HF 强制监听 7860 端口，Dockerfile 已处理
- README 顶部的 HF 链接部署完成后替换为你的真实 Space 地址

## 方式三：本机 + cpolar 内网穿透（面试当天演示）

1. 启动本地服务：双击 `start.bat`（或 `./start.sh`）
2. 注册 [cpolar](https://www.cpolar.com)（国内服务，注册免费，无需梯子），
   下载 Windows 版并安装
3. 打开 cpolar，创建隧道：协议 `http`，本地端口 `8000`
4. 复制分配的公网地址（形如 `xxxx.r2.cpolar.top`），发给面试官即可
5. 演示前自查：手机流量（关 WiFi）打开该地址，能刷出岗位列表就稳了

**面试日检查清单**：
- [ ] start.bat 已运行，http://127.0.0.1:8000 正常
- [ ] cpolar 隧道在线，公网地址手机可访问
- [ ] （可选）提前跑一次 `python main.py crawl` 让"今日更新"数字好看

## 方式四：Docker Compose（有云服务器时）

```bash
git clone https://github.com/FanXiaofu/job-radar.git && cd job-radar
cp .env.example .env   # 填 LLM_API_KEY
docker compose up -d --build
# 访问 http://服务器IP:8000，数据持久化在 ./data
```

可选 Compose 变量（写在 `.env` 或命令前）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `HOST_PORT` | 8000 | 宿主机端口 |
| `DATA_DIR` | ./data | SQLite 数据目录挂载 |
| `LOG_DIR` | ./logs | 日志目录挂载 |

建议同步在服务器安全组只放行 80/443/22，并用 Nginx 反代 + 域名。
