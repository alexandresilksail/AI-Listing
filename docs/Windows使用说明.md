# Windows 使用说明

> 适用：Windows 10 / 11，PowerShell 或 Git Bash。目标：在桌面浏览器（Chrome / Edge）中跑通完整流程。

## 一、准备环境

需要三项，缺一不可：

| 组件 | 版本要求 | 检查命令 |
|------|---------|---------|
| Python | 3.12 及以上 | `python --version` |
| Node.js | 18 及以上（推荐 20/22） | `node --version` |
| npm | 随 Node 附带 | `npm --version` |

没有的话：Python 从 https://www.python.org/downloads/ 安装（**务必勾选 Add Python to PATH**）；Node 从 https://nodejs.org/ 安装 LTS 版。

## 二、启动（两种方式任选）

### 方式 A：一键脚本（推荐）

双击项目根目录下的 `scripts/start_dev.bat`。脚本会自动：

1. 探测 Python 解释器（优先 `.venv`，其次已配置的项目虚拟环境）
2. **首次运行自动创建 `.venv` 并安装后端依赖**（`pip install -r requirements.txt`）
3. **首次运行自动安装前端依赖**（`npm install`）
4. 等待后端健康检查就绪后，启动前端 `http://127.0.0.1:5173`
5. 自动打开浏览器

> V1.1 起首次启动不再需要手动装依赖；断网或安装失败时脚本会明确报错并退出。

### 方式 B：手动启动（便于排错）

打开**两个**终端窗口，分别执行。

**终端 1 —— 后端**

```bat
cd /d C:\path\to\polylisting-ai\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

看到 `PolyListing AI 后端已启动，任务队列运行中` 即成功。

**终端 2 —— 前端**

```bat
cd /d C:\path\to\polylisting-ai\frontend
npm install
npm run dev
```

看到 `Local: http://localhost:5173/` 即成功。

浏览器访问 **http://127.0.0.1:5173**（推荐用 Chrome 或 Edge）。

> 前端 Vite 已配置 `/api` 代理转发到 `127.0.0.1:8000`，无需额外配置跨域。

### 关于 API 令牌（V1.1 起）

V1.1 起所有 API 默认要求令牌（健康检查除外）。本地开发二选一：

1. **不配置**：后端启动时打印黄色警告，接口全部可用——适合本机单人试用。
2. **配置令牌**：在 `backend/.env` 中写一行 `PL_API_TOKEN=任意长随机串`（可参考 `backend/../.env.example`），重启后端。前端首次请求会弹框要求输入令牌，输入后存入浏览器 localStorage，之后自动携带，不再询问。

> 生产环境（`PL_ENV=production`）**必须**配置 `PL_API_TOKEN`，否则后端拒绝启动——这是有意的安全设计，防止管理接口裸奔。

## 三、五分钟跑通完整流程

1. **载入演示数据**：进入「工作台」，点右上角 **载入演示数据** → 自动创建 3 个演示 SKU 与演示图片。
2. **生成 Listing**：「Listing 生成」页 → 选商品 → 平台选 Amazon → 勾选 **美国 / 德国 / 日本** → 开始生成。任务列表轮询至「已完成」，点任务行查看标题、五点卖点、详情、FAQ。
3. **SEO 优化**：「SEO 工作台」→ 选商品与市场 → 生成关键词与标题候选 → 查看四维评分与覆盖率分析。
4. **生成图片**：「图片工作台」→ 选商品 → 勾选参考原图 → 依次生成 **主图优化 / 场景图 / 信息图** → 网格查看生成图。
5. **人工审核**：「图片审核中心」→ 点击图片类风险项 → 原图与生成图左右对比 → 通过 / 驳回 / 标记已处理。
6. **导出**：「导出中心」→ 选「完整商品内容包」→ 选商品 → 生成并下载 ZIP。

## 四、常见 Windows 问题

**Q：端口 8000 或 5173 被占用？**
```powershell
netstat -ano | findstr :8000
taskkill /PID <上一步查到的PID> /F
```
或换端口：`uvicorn app.main:app --port 8010`，前端在 `vite.config.ts` 里同步改 `target`。

**Q：pip 安装 Pillow / pandas 报编译错误？**
安装依赖时用了 Python 3.13 一般没问题（Pillow 11 提供预编译 wheel）。若仍失败：
```bat
python -m pip install --upgrade pip
pip install -r requirements.txt --only-binary=:all:
```

**Q：npm install 卡住或报证书错误？**
```bat
npm config set registry https://registry.npmmirror.com
npm install
```

**Q：中文乱码（终端显示问号）？**
在 PowerShell 执行：`chcp 65001` 后重开终端。

**Q：浏览器打开是空白页？**
按 F12 看 Console。大概率是后端没起来——先用 `curl http://127.0.0.1:8000/api/health` 或浏览器访问该地址确认返回 `{"status":"ok",...}`。

**Q：所有请求返回 401 Unauthorized？**
后端配置了 `PL_API_TOKEN` 而前端没有。前端会在 401 时弹框要求输入令牌——输入与 `backend/.env` 中 `PL_API_TOKEN` 相同的值即可。想清除已存令牌：浏览器 DevTools → Application → Local Storage → 删除 `pl_api_token`。

**Q：后端启动即退出，提示「PL_ENV=production 但未配置 PL_API_TOKEN」？
这是有意的 fail-fast 设计。本地开发请把 `.env` 里的 `PL_ENV` 设为 `development`（或删掉该行），或补一个 `PL_API_TOKEN`。

## 五、数据存在哪里

| 内容 | 路径 |
|------|------|
| SQLite 数据库 | `backend/data/polylisting.db` |
| 原始商品图 / 生成图 | `backend/data/images/` |
| 导出文件 | `backend/data/exports/` |
| 模型 API 配置 | `backend/data/runtime_settings.json`（权限 600，切勿外传） |

清空演示数据：删除上述 `backend/data` 目录即可恢复初始状态。
