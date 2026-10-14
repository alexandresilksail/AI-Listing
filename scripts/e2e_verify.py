"""端到端验证脚本：带 API 令牌跑完整工作流。

用法：
    PL_API_TOKEN=xxx python scripts/e2e_verify.py [--base http://127.0.0.1:8000]

覆盖：演示种子 → 多市场 Listing 生成（模拟模式）→ 图片生成 → 审核 → 4 种导出。
输出 JSON 摘要，任一步骤失败即非零退出。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# 本地便捷：命令行未提供令牌时，从 backend/.env 读取（与后端同一配置源）
if not os.environ.get("PL_API_TOKEN"):
    env_file = Path(__file__).resolve().parent.parent / "backend" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("PL_API_TOKEN="):
                os.environ["PL_API_TOKEN"] = line.split("=", 1)[1].strip()

RESULT: dict = {"steps": [], "ok": True}


def step(name: str, fn) -> object:
    try:
        value = fn()
        RESULT["steps"].append({"step": name, "status": "ok", "detail": value})
        print(f"[OK] {name}: {json.dumps(value, ensure_ascii=False)[:300]}")
        return value
    except Exception as exc:  # noqa: BLE001
        RESULT["ok"] = False
        RESULT["steps"].append({"step": name, "status": "fail", "detail": str(exc)[:500]})
        print(f"[FAIL] {name}: {exc}")
        raise


def call(base: str, token: str, method: str, path: str, body: dict | None = None,
         timeout: float = 30) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-API-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw[:300]


def wait_task(base: str, token: str, kind: str, task_id: int,
              timeout: float = 90) -> dict:
    path = f"/api/listings/tasks/{task_id}" if kind == "listing" else f"/api/images/tasks/{task_id}"
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        code, payload = call(base, token, "GET", path)
        last = payload if isinstance(payload, dict) else {}
        status = str(last.get("status", ""))
        if status in {"completed", "failed"}:
            return last
        time.sleep(1)
    raise TimeoutError(f"{kind} 任务 {task_id} 超时，最后状态: {last.get('status')} 详情: {str(last)[:200]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=os.environ.get("PL_BASE", "http://127.0.0.1:8000"))
    args = parser.parse_args()
    base = args.base.rstrip("/")
    token = os.environ.get("PL_API_TOKEN", "")
    if not token:
        print("错误：需要 PL_API_TOKEN 环境变量")
        return 2

    # 0. 健康检查（公开端点，无令牌）
    code, payload = call(base, "", "GET", "/api/health", timeout=10)
    assert code == 200, f"health 期望 200 实得 {code}: {payload}"
    print(f"[OK] health: {payload}")

    # 1. 演示种子（幂等）
    code, seed = call(base, token, "POST", "/api/demo/seed")
    step("演示种子", lambda: seed)
    assert code == 200, f"seed 期望 200 实得 {code}: {seed}"

    # 2. 取演示商品
    code, products = call(base, token, "GET", "/api/products")
    step("商品列表", lambda: {"count": len(products) if isinstance(products, list) else 0})
    assert code == 200 and isinstance(products, list) and products, "商品列表为空"
    product_id = products[0]["id"]

    # 3. 多市场 Listing 生成（模拟模式），返回每市场一个任务
    code, tasks = call(base, token, "POST", "/api/listings/tasks",
                       {"product_id": product_id, "platform": "amazon",
                        "markets": ["US", "DE", "JP"]})
    step("提交 Listing 任务(US/DE/JP)", lambda: {"task_ids": [t.get("id") for t in tasks]})
    assert code in (200, 201), f"提交 listing 任务失败 {code}: {tasks}"
    for t in tasks:
        done = wait_task(base, token, "listing", t["id"])
        step(f"Listing 任务 {t['id']} 完成", lambda: {"status": done.get("status"),
                                                     "market": done.get("market"),
                                                     "cost_usd": done.get("cost_usd"),
                                                     "cost_known": done.get("cost_known")})
        assert done.get("status") == "completed", f"listing 任务未完成: {str(done)[:300]}"

    # 4. 图片生成（模拟模式）
    code, img_task = call(base, token, "POST", "/api/images/tasks",
                          {"product_id": product_id, "image_type": "scene", "platform": "amazon",
                           "market": "US", "aspect_ratio": "1:1", "count": 2})
    step("提交图片任务", lambda: {"task_id": img_task.get("id"), "status": img_task.get("status")})
    assert code in (200, 201), f"提交图片任务失败 {code}: {img_task}"
    image_task = wait_task(base, token, "image", img_task["id"])
    step("图片任务完成", lambda: {"status": image_task.get("status"),
                                 "generated": image_task.get("generated_count") or image_task.get("succeeded") or "?"})
    assert image_task.get("status") == "completed", f"图片任务未完成: {str(image_task)[:300]}"

    # 5. 取版本并审核（versions 路由直接返回列表）
    code, versions = call(base, token, "GET", f"/api/listings/versions?product_id={product_id}")
    step("版本列表", lambda: {"count": len(versions) if isinstance(versions, list) else 0})
    assert code == 200 and isinstance(versions, list) and versions, f"版本列表失败 {code}: {versions}"
    version_id = versions[0]["id"]
    code, review = call(base, token, "POST", f"/api/listings/versions/{version_id}/review", {})
    step("审核版本", lambda: {"issues": len(review.get("items", [])) if isinstance(review, dict) else "?"})
    assert code == 200, f"审核失败 {code}: {review}"

    # 6. 四种导出
    export_types = ["listing_csv", "listing_xlsx", "images_zip", "full_package"]
    for exp_type in export_types:
        body = {"type": exp_type, "product_id": product_id}
        if exp_type == "images_zip":
            code, images = call(base, token, "GET", "/api/images/generated")
            items = images if isinstance(images, list) else images.get("items", [])
            if items:
                body["image_ids"] = [it["id"] for it in items[:2]]
        code, exp = call(base, token, "POST", "/api/exports", body, timeout=60)
        step(f"导出 {exp_type}", lambda: {"export_id": exp.get("id"), "status": exp.get("status")})
        assert code in (200, 201), f"导出 {exp_type} 失败 {code}: {exp}"
        export_id = exp["id"]
        deadline = time.time() + 60
        while time.time() < deadline:
            code, detail = call(base, token, "GET", f"/api/exports/{export_id}")
            if isinstance(detail, dict) and detail.get("status") in {"completed", "failed"}:
                break
            time.sleep(1)
        step(f"导出 {exp_type} 完成", lambda: {"status": (detail or {}).get("status"),
                                              "file": (detail or {}).get("file_name")})
        assert isinstance(detail, dict) and detail.get("status") == "completed", f"导出未完成: {str(detail)[:200]}"

    # 7. 任务总览（含未知费用统计）
    code, overview = call(base, token, "GET", "/api/tasks/overview")
    step("任务总览", lambda: overview)
    assert code == 200

    print("\n==== e2e 结果 ====")
    print(json.dumps({"ok": RESULT["ok"], "steps": len(RESULT["steps"])}, ensure_ascii=False))
    return 0 if RESULT["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
