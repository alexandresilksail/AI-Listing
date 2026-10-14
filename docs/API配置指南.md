# 文本模型与图像模型 API 配置指南

本项目通过 **OpenAI 兼容接口** 接入 AI 能力，不绑定任何特定供应商。凡是提供 OpenAI 兼容 `/chat/completions`、`/images/generations`、`/images/edits` 接口的服务均可接入。

## 一、在界面中配置（推荐）

「模型设置」页面填写后点「保存」，配置落盘到服务端 `backend/data/runtime_settings.json`（权限 600）。

| 字段 | 说明 | 示例 |
|------|------|------|
| 文本 API Base | OpenAI 兼容地址，结尾不要带 `/` | `https://api.openai.com/v1` |
| 文本 API Key | 服务端保存，界面只显示脱敏值 | `sk-****abcd` |
| 文本模型 | Chat Completions 模型名 | `gpt-4o-mini` |
| 图像 API Base / Key / 模型 | 同上 | `gpt-image-1` |

点「测试连接」验证：文本模型会发一条极短请求并检查 HTTP 状态；图像模型会调用 `/models` 列模型。

> **Key 留空表示不修改**。要清空某项，请填写一个空格后保存。

## 二、通过环境变量配置

适合服务器部署。复制 `.env.example` 为 `.env` 填写：

```ini
PL_TEXT_API_BASE=https://api.openai.com/v1
PL_TEXT_API_KEY=sk-xxxxx
PL_TEXT_MODEL=gpt-4o-mini
PL_IMAGE_API_BASE=https://api.openai.com/v1
PL_IMAGE_API_KEY=sk-xxxxx
PL_IMAGE_MODEL=gpt-image-1
```

Docker Compose 会自动读取宿主 `.env` 并注入容器。

**优先级**：环境变量 → `.env` → `runtime_settings.json`（后者仅在非空时覆盖）。

## 三、文本模型要求

- 接口：`POST {base_url}/chat/completions`，鉴权头 `Authorization: Bearer <key>`
- 必须支持 `response_format: {"type":"json_object"}`（JSON 输出模式）
- 返回体需含 `choices[0].message.content`，可选 `usage.prompt_tokens` / `usage.completion_tokens`

| 已知可用 | 备注 |
|---------|------|
| OpenAI gpt-4o-mini | 默认推荐，成本低，支持 JSON 模式 |
| OpenAI gpt-4o | 质量更好，成本约高 20 倍 |
| 各类 OpenAI 兼容网关 | 只要支持 JSON 模式即可，如 DeepSeek / 通义 / 智谱等的兼容端点、以及自建 One-API / New API |

> 若使用国内模型厂商的兼容端点，注意确认其支持 **JSON 输出模式**，否则 Listing 结构化生成会失败。可选 gpt-4o-mini 级别的低价模型即可。

### 成本估算（V1.1：三态模型）

代码内建价格表（`app/services/ai/base.py` 的 `PRICING`）。V1.1 起费用分**三种状态**：

| 状态 | 记录值 | 界面表现 |
|------|--------|---------|
| 实际费用 | `cost_usd` 数值 + `cost_known=true` | 正常显示金额 |
| 估算费用 | 按价格表推算 + `cost_known=true` | 正常显示金额 |
| **未知费用** | `cost_usd=NULL` + `cost_known=false` | 琥珀色「未知」徽章，**绝不按 0 计** |

| 模型 | 输入（$/1K tokens） | 输出（$/1K tokens） |
|------|------------------|------------------|
| gpt-4o-mini | 0.00015 | 0.0006 |
| gpt-4.1-mini | 0.0004 | 0.0016 |
| gpt-4o | 0.0025 | 0.01 |

单个市场一次 Listing 生成估算（gpt-4o-mini）：约 **1~2 分钱人民币**。

**未知模型价格管控**：使用价格表之外的模型时，可通过 `PL_UNKNOWN_COST_POLICY` 控制：

- `allow`（默认）：放行执行，费用记为「未知」，任务总览可查看「今日未知费用调用数」——先跑通再补价格
- `block`：直接拒绝执行，逼你先把价格补进 `PRICING`——成本敏感场景推荐

**JSON 输出模式**：文本模型默认请求 `response_format: json_object`。遇到不支持的供应商返回 400 时自动降级重试（无需手动干预）；如降级仍失败，可设 `PL_TEXT_JSON_MODE=false` 彻底关闭 JSON 模式（解析失败率会上升，请谨慎）。

## 四、图像模型要求

- 生成：`POST {base_url}/images/generations`，body `{model, prompt, size, n}`
- 编辑（使用参考图）：`POST {base_url}/images/edits`，multipart `{image, model, prompt, size, n}`
- 返回：`data[].b64_json` 或 `data[].url`

支持的画幅：

| 界面选项 | 请求 size | 说明 |
|---------|----------|------|
| 1:1 | 1024x1024 | 亚马逊主图推荐 |
| 3:4 / 9:16 | 1024x1536 | 竖版，适合详情页 |
| 4:3 / 16:9 | 1536x1024 | 横版，适合品牌横幅 |

> 不同模型支持的尺寸不同（如 dall-e-3 只支持 1024x1024 / 1792x1024 / 1024x1792）。若返回 400，请在设置里换成支持该尺寸的模型。

参考图说明：勾选商品原图后会走「编辑」接口，把第一张参考图作为 `image` 上传，最大程度保持商品外观一致。

### 成本

| 模型 | 每张费用（内置估算） |
|------|------------------|
| gpt-image-1 | $0.04 |
| dall-e-3 | $0.04 |
| dall-e-2 | $0.02 |

## 五、预算控制

界面「每日预算」与「单任务预算」会在任务**执行前**校验（V1.1 起带线程锁，防止并发任务同时穿过预算线）：

- 预估成本超过单任务预算 → 拒绝执行并提示
- 当日累计 + 本次预估超过每日预算 → 拒绝执行并提示
- 预估为「未知」时：按 `PL_UNKNOWN_COST_POLICY` 决定放行还是拒绝，且不计入已花费统计（总览单独展示「未知费用调用数」）

在「模型设置」页底部的调用日志表可查看每次调用的 provider、模型、用途、状态、耗时、费用（含「未知」标记）。

> 模拟模式不产生任何费用，也不计入预算。

## 六、常见问题

**Q：填了 Key 但仍是模拟模式？**
检查 API Base 是否带 `/v1`（多数服务需要）、Key 是否有该模型权限、模型名是否拼错。用「测试连接」看返回的 HTTP 状态码与消息：401 通常是 Key 无效，404 通常是模型名或 Base 地址错误。

**Q：生成 Listing 一直失败？**
大概率是模型不支持 JSON 输出模式，或输出被截断。换用支持 `response_format: json_object` 的模型，或提高超时（`PL_REQUEST_TIMEOUT_SEC`）。

**Q：图片生成返回 400 size not supported？**
当前模型不支持所选画幅，改 1:1 或换模型（如 gpt-image-1）。V1.1 起按模型自动映射尺寸（如 dall-e-3 仅支持 1024x1024 / 1792x1024 / 1024x1792），会优先选择该模型支持的最近尺寸，仍不支持时报错信息会明确说明。

**Q：调用日志里费用显示「未知」？**
所用模型不在内置价格表内。补一行 `PRICING`（`app/services/ai/base.py`）即可；或设 `PL_UNKNOWN_COST_POLICY=block` 强制必须先补价格。

**Q：供应商返回 400 关于 response_format？**
V1.1 起会自动降级（去掉 `response_format` 重试一次）。若你的供应商两种模式都不稳定，设 `PL_TEXT_JSON_MODE=false`。

**Q：想换供应商怎么办？**
只需在设置里改三个字段。若要接入接口协议不同的供应商，新增一个适配器类继承 `TextAdapter` / `ImageAdapter`（见 `app/services/ai/base.py`），并在 `registry.py` 注册即可，业务层无需改动。

## 七、密钥安全

- Key 只保存在服务端：环境变量或 `data/runtime_settings.json`（600 权限）
- 所有 API 响应返回的都是脱敏字段（如 `sk-****abcd`），测试 `test_settings_masks_api_key` 对此有强制校验
- 日志不输出密钥，异常信息也不含密钥
- 切勿把 `.env` 与 `runtime_settings.json` 提交到版本库
