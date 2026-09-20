# 部署指南

三种方式，按场景选择：

| 方式 | 成本 | 适用场景 |
|---|---|---|
| Hugging Face Spaces | 免费 | 简历链接，长期在线（国内访问偶尔慢） |
| 本机 + cpolar | 免费 | 面试当天演示，流畅稳定 |
| Docker Compose | 需一台服务器 | 有云服务器时的最佳方案 |

---

## 方式一：Hugging Face Spaces（免费长期在线）

1. **注册** [huggingface.co](https://huggingface.co)（邮箱即可，免费）
2. 右上角头像 → New Space：
   - Space name：`job-radar`
   - SDK：选 **Docker**（Blank 模板）
   - Visibility：Public
3. 把本仓库代码推送到 Space 的 git 仓库（Space 页面有仓库地址，形如
   `https://huggingface.co/spaces/<你的用户名>/job-radar`）：

   ```bash
   git remote add hf https://huggingface.co/spaces/<用户名>/job-radar
   git push hf main
   ```

   推送时用户名填 HF 用户名，密码填 HF Access Token
   （头像 → Settings → Access Tokens → 新建，勾 write 权限）
4. **配置 Secret**（密钥不进代码库）：Space 页面 → Settings → Variables and secrets
   → New secret：`LLM_API_KEY` = 你的 DeepSeek Key
5. 等 Docker 自动构建（首次 5~10 分钟），Build 日志在页面顶部可见
6. 验证：打开 Space URL，页面出现岗位列表即成功；`<Space URL>/health` 返回 JSON

**注意事项**：
- 免费版 Space 重建后 SQLite 数据丢失，应用启动时会检测空库自动重新采集（首轮约 4–8 分钟），
  期间页面显示"暂无岗位数据"属正常
- HF 强制监听 7860 端口，Dockerfile 已处理
- README 顶部的 HF 链接部署完成后替换为你的真实 Space 地址

## 方式二：本机 + cpolar 内网穿透（面试当天演示）

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

## 方式三：Docker Compose（有云服务器时）

```bash
git clone https://github.com/FanXiaofu/job-radar.git && cd job-radar
cp .env.example .env   # 填 LLM_API_KEY
docker compose up -d --build
# 访问 http://服务器IP:8000，数据持久化在 ./data
```

建议同步在服务器安全组只放行 80/443/22，并用 Nginx 反代 + 域名。
