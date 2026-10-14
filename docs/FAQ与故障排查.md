# 常见问题与故障排查

## 一、启动类

### 后端启动报 `ModuleNotFoundError: No module named 'app'`
未在项目 `backend/` 目录下执行，或虚拟环境未激活。先 `cd backend`，Windows 用 `.venv\Scripts\activate`，Linux 用 `source .venv/bin/activate`。

### `ImportError: attempted relative import beyond top-level package`
必须从 `backend/` 目录运行 uvicorn，不能在 `backend/app/` 内运行。正确命令：
```bash
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 端口被占用
```bash
# Linux/Mac
lsof -i :8000
# Windows PowerShell
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```
或换端口启动 `--port 8010`。

### 前端白屏 / 404
1. 确认后端健康：`curl http://127.0.0.1:8000/api/health`
2. 确认 Vite 代理生效（`vite.config.ts` 中 `/api` → `http://127.0.0.1:8000`），若后端换了端口需同步修改 `target`
3. F12 Console 查看具体报错

## 二、生成类

### 生成的 Listing 全是「[模拟·待补充]」
正常行为——**未配置文本模型 API**。前往「模型设置」填写 API Base / Key / 模型名并保存，然后重新生成。判定依据：任务行的 `is_simulated` 字段与界面上的「⚠ 模拟演示」徽章。

### 单字段重新生成报错「文本模型 API 未配置」
这是**刻意设计**：无真实模型时不允许伪造重生成结果。配置 API 后即可使用。

### 任务一直停留在「待处理」
`get_queue()` 的 worker 应在 lifespan 启动时运行。检查后端日志是否有 `PolyListing AI 后端已启动，任务队列运行中`。若无，重启服务；若任务显示「失败」，查看任务行的错误信息。

### 任务失败常见原因
| 错误信息 | 原因与处理 |
|---------|-----------|
| `401 / Incorrect API key` | Key 无效或过期 |
| `404 model_not_found` | 模型名错误，或账号无该模型权限 |
| `429 rate limited` | 触发速率限制，稍后重试（内置有限重试，仍失败请降低并发/数量） |
| `超时` | 提高 `PL_REQUEST_TIMEOUT_SEC`（默认 120s） |
| `size not supported` | 该图像模型不支持所选画幅，改为 1:1 或更换模型 |

### 生成图带 SIMULATED 水印、界面出现红色警示
未配置图像模型 API 时的占位图。**这是占位图，不是真实商品图，禁止用于发布**（系统已自动生成高风险审核项）。配置图像 API 后重新生成。

### 生成图与原图外观不一致
这是生成式模型的固有风险。系统已内置两道防线：
1. 提示词强制携带「必须保留」（轮廓/颜色/材质/结构/配件/Logo/比例）约束
2. 自动生成 `manual_visual_check` 审核项，要求人工比对后再通过

建议：优先使用「主图优化 + 参考原图」模式，把视觉偏差控制在最小。

## 三、导出类

### 导出文件大小为 0 或下载后打不开
检查 `backend/data/exports/` 是否有对应文件。目录不存在或权限不足时写入会失败，导出任务状态会变为 `failed` 并在「错误」列显示原因。

### 导出的 XLSX 在 Excel 中提示格式问题
项目使用 openpyxl 写入，若仍异常请更新 Office 或改用 CSV 导出。

### ZIP 解压后图片命名规则
`{SKU}/{市场}/{图片类型}/{文件名}.png`，根目录 `manifest.json` 记录每张图的尺寸、版本、是否模拟、生成提示词，方便追溯。

### 完整商品包里缺图片
该 SKU 尚未生成对应类型的图片。先到「图片工作台」生成，再导出。

## 四、数据与存储类

### 上传图片失败
| 提示 | 处理 |
|------|------|
| `不支持的图片格式` | 仅支持 jpg / jpeg / png / webp |
| `图片超过大小限制` | 默认单图 ≤10MB，可在模型设置里调 `max_upload_mb` |
| `文件内容不是有效的图片` | 文件损坏或伪造扩展名（魔数校验失败） |

### 删除商品后磁盘没释放
系统会清理关联的原图与生成图文件。若仍有残留，检查 `backend/data/images/products/{商品ID}/`。

### 数据库锁死（SQLite）
开发环境 SQLite 在高并发下可能锁库。生产请切换 PostgreSQL（见 Linux 部署指南）。

### 清空所有数据
删除 `backend/data` 目录后重启服务即可（会自动重建）。

## 五、安全相关

### 担心 API Key 泄露
- Key 只写进 `backend/data/runtime_settings.json`（600 权限）或环境变量
- 所有 API 响应返回脱敏值，测试 `test_settings_masks_api_key` 强制校验
- 若怀疑泄露：立刻到供应商后台吊销并重新生成 Key，然后在「模型设置」页更新

### 演示数据是真实的吗
`demo/` 下的商品图片是程序绘制的示意图，图上已标注「仅供功能演示，非真实商品照片」，不可用作品图素材。

## 六、发现 Bug 怎么办

1. 后端终端/日志查看完整 traceback
2. 记录复现步骤：操作页面 → 接口 → 返回的错误信息
3. 跑一遍自动化测试确认是否破坏既有功能：

```bash
cd backend
pytest tests -v
```

参考最近一次基线结果：[`测试报告.md`](测试报告.md)（36 项全部通过）。
