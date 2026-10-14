# PolyListing AI

面向亚马逊、Temu、独立站中小卖家的 AI 跨境电商 Listing 与商品图片生成平台。

> **核心工作流**：上传商品资料与图片 → 选择销售市场和平台 → 生成本地化多语种 Listing → 生成商品营销图片 → 自动检查文案与图片风险 → 人工审核 → 批量导出。

本文档是项目主说明。配套文档见 `docs/` 目录。

---

## ⚠ 使用前必读：关于「模拟模式」

本项目所有 AI 能力通过**可替换适配器**接入，**不内置任何模型凭证**。

| 状态 | 表现 | 数据标记 |
|------|------|----------|
| **未配置 API（默认）** | 所有生成结果与带上 `SIMULATED` 水印的占位图 | `is_simulated = true`，UI 红框「⚠ 模拟演示」警示，审核中心自动产生 **高风险** 待处理项 |
| **已配置 API** | 真实调用 OpenAI 兼容接口，记录模型名、耗时、费用、token | `is_simulated = false`，UI 绿色「真实 AI 生成」 |

硬性约定（已在代码与测试中强制）：

- **未配置 API 时不得把模拟内容标记为真实 AI 结果**。
- 模拟占位图明确标注「模拟占位图 · 未配置图像模型 API」，不含任何真实商品视觉。
- 单字段重新生成在无 API 时**直接返回错误**，不伪造内容。
- SEO 关键词**不虚构搜索量、竞争度、排名、流量数据**，统一标注「AI 关键词建议」。
- AI 检查**不替代平台官方审核**；无法确认的规则一律标记「需人工核实」。

这意味着：**不花一分钱就能跑通全流程**（导入 → 生成 → 审核 → 导出），接入 Key 后同一套操作即可产出真实结果。

---

## 已实现能力清单

### ✅ 商品资料管理
- 单品手动录入 / 粘贴中文详情 / CSV·XLSX·TXT 批量导入（`backend/app/routers/products.py`）
- 商品主图、实物图、细节图、包装图、场景参考图、Logo 上传，分类管理与删除
- 从中文详情**启发式提取结构化参数**（材质/尺寸/颜色/重量/容量/包装清单/注意事项…），提取结果默认 `verified=false`，需人工确认后才可用于生成
- 严格保留「原始资料 ↔ 图片 ↔ SKU」关联；删除商品会清理关联文件

### ✅ 多语种 Listing 生成（11 个市场）
美国/英国/德国/法国/西班牙/意大利/日本/巴西/印尼/泰国/沙特阿拉伯，支持同一 SKU 一次勾选多市场批量生成。
产出字段：标题、五点卖点、商品详情、FAQ、后台搜索词、图片 ALT、营销标语、本地化说明、风险提示。

本地化策略按目标市场调整语气、单位制、拼写习惯（美式/英式）、查找方式与购买场景；禁止生硬直译。

### ✅ AI SEO 优化引擎
- 关键词推导（核心词 / 属性词 / 场景词 / 长尾词），可按市场调整场景词库
- 多个标题候选 + 四维评分（总体 / 长度合规 / 关键词覆盖 / 可读性）
- 关键词在标题/卖点/详情中的自然融入度分析、重复堆砌检测
- 「必须包含 / 禁用」词表，未命中或命中会有可视化告警

### ✅ AI 商品图片生成
六种图片类型：**主图优化 / 场景图 / 卖点图 / 信息图 / 品牌营销图 / 多语言图片本地化**（阿拉伯语支持 RTL 排版）。

- 支持上传商品原图作为参考图（走图像编辑接口），生成图作为**独立版本**保存，绝不覆盖原图
- 画幅比例 `1:1 / 3:4 / 4:3 / 9:16 / 16:9`，生成数量 1–4，可设风格/背景/自定义提示词
- 提示词由系统自动构建，强制包含「必须保留」（轮廓/颜色/材质/结构/Logo/配件/比例）与「禁止」（虚构配件、修改 Logo、伪造认证数据）约束
- 真实性边界：对外观易偏差的商品生成图，自动生成「需人工与原图比对」的审核项

### ✅ 规则与内容审核
文案侧：字段长度、平台限制、绝对化/夸大用语（多语言词表）、需证据的认证宣称、关键词堆砌、禁用词、必含词缺失、语言残留。
图片侧：分辨率、文件格式、主图背景白度采样检测、模拟图识别、外观与文字准确性人工核实项。

每条风险记录：**等级 / 原因 / 位置 / 修改建议 / 是否需人工核实**。规则可按平台·市场·类目配置，并记录来源与更新时间。

### ✅ 批量任务与成本管理
asyncio 后台队列 + 单 worker，架构可平滑替换为 Celery / Redis。支持幂等去重（防止重复点击导致重复扣费）、失败重试、单任务预算、每日预算、调用耗时与费用记录，文本与图片分别统计。

### ✅ 导出与交付
- 文案导出 XLSX / CSV（含 CSV 公式注入防护），可按 SKU/市场/平台/语言筛选
- 图片 ZIP 打包（含 manifest.json 记录尺寸、是否模拟、版本、提示词）
- **完整商品内容包**：商品资料 JSON + 各市场 Listing MD + SEO 关键词/标题 CSV + 原图 + 生成图 + 审核报告 JSON

> 生成文件 ≠ 完成平台发布。项目**未实现**任何平台直连发布功能。

---

## 界面页面（11 个）

工作台 · 商品管理 · Listing 生成 · SEO 工作台 · 图片工作台 · 文案编辑器 · 图片审核中心 · 批量任务 · 导出中心 · 模型设置 · 规则中心

---

## 技术栈

| 层 | 选型 |
|----|------|
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS + React Router |
| 后端 | Python 3.12+ / FastAPI + SQLAlchemy 2.0 + Pydantic v2 |
| 数据库 | SQLite（开发环境），可通过 `PL_DATABASE_URL` 切换 PostgreSQL |
| 数据处理 | pandas + openpyxl（Excel）、Pillow（图片） |
| 任务 | asyncio 队列（内建，可替换 Celery + Redis） |
| 迁移 | Alembic（`migrations/`） |
| 测试 | pytest + FastAPI TestClient |
| 部署 | Docker Compose + Nginx |

---

## 目录结构

```
polylisting-ai/
├── backend/
│   ├── app/
│   │   ├── config.py            # 配置（含运行时 ⚙ 模型设置持久化）
│   │   ├── models.py            # 13 张表的数据模型
│   │   ├── schemas.py           # Pydantic 请求/响应模型
│   │   ├── serializers.py       # 模型 → Schema 序列化
│   │   ├── security.py          # 上传校验 / 路径穿越 / 公式注入 / 密钥脱敏
│   │   ├── routers/             # 11 个 API 路由模块
│   │   ├── services/
│   │   │   ├── ai/              # 可替换适配器：base / openai_text / openai_image / registry
│   │   │   ├── listing_service.py
│   │   │   ├── image_service.py
│   │   │   ├── seo_service.py
│   │   │   ├── review_service.py
│   │   │   ├── export_service.py
│   │   │   ├── task_queue.py
│   │   │   ├── storage.py       # 可替换存储接口
│   │   │   └── market_data.py   # 市场语言包与规则基线
│   │   └── main.py
│   ├── tests/                   # pytest 自动化测试（36 项）
│   ├── migrations/              # Alembic
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/               # 11 个页面
│   │   ├── components/          # Layout + UI 组件库
│   │   ├── api/client.ts        # API 客户端
│   │   └── types.ts
│   └── vite.config.ts
├── demo/sample_products.csv     # 演示商品导入样例
├── docs/                        # 配套文档
├── scripts/                     # Windows / Linux 启动脚本
├── deploy/nginx.conf
├── docker-compose.yml
└── .env.example
```

---

## 快速开始（无 API Key，立即可用）

```bash
# Windows：双击 scripts/start_dev.bat
# Linux / macOS：
bash scripts/start_dev.sh
```

或手动：

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端（新开终端）
cd frontend
npm install
npm run dev
```

浏览器访问 **http://127.0.0.1:5173**，点击工作台右上角「载入演示数据」即可体验完整流程。

详细步骤见：
- Windows：[`docs/Windows使用说明.md`](docs/Windows使用说明.md)
- Linux 服务器：[`docs/Linux部署指南.md`](docs/Linux部署指南.md)
- API 接入：[`docs/API配置指南.md`](docs/API配置指南.md)
- 问题排查：[`docs/FAQ与故障排查.md`](docs/FAQ与故障排查.md)

---

## 运行测试

```bash
cd backend
pip install -r requirements.txt
pytest tests -v
```

最近一次真实测试结果：**36 passed**（见 `docs/测试报告.md`）。

---

## 安全设计

- API Key **仅保存在服务端**（环境变量或 `data/runtime_settings.json`，文件权限 600），API 响应中**永远返回脱敏字段**，日志中不输出密钥（有测试覆盖）
- 上传校验：扩展名白名单 + 文件大小限制 + **文件魔数（magic bytes）校验**，伪造扩展名会被拒绝
- 路径穿越防护：所有文件读写经 `safe_join` 校验目标必须在存储根目录内
- CSV 导出公式注入防护：`= + - @` 前缀自动转义
- 幂等去重：相同任务提交复用同一幂等键，避免重复扣费
- 模型调用：超时、有限重试、预估成本超预算直接拒绝

---

## 已知限制（诚实说明）

1. **未实现平台直连发布**——规范明确要求只有真实实现并验证官方 API 后才可提供，本项目仅限导出。
2. **未接入真实搜索量数据源**——SEO 模块只输出 AI 关键词建议，不含任何搜索量/竞争度数据。
3. **图片文字准确性依赖人工校对**——生成图上的文字由模型渲染，系统强制产生「需人工校对」审核项。
4. **参数提取为启发式**——从中文详情抽取的参数默认未验证，需用户确认后才视为可信事实。
5. **规则基线需以平台官方最新规则为准**——内置规则均标记 `needs_verify`。
6. 内建任务队列为单 worker，大规模并发场景建议替换为 Celery + Redis（接口已按此设计）。
