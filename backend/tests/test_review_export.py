"""审核、导出、设置、规则与安全测试。

重点验证：
- 模拟内容不得被标记为真实 AI 结果
- 密钥不在任何 API 响应中明文出现
- 路径穿越 / CSV 公式注入防护
"""
from __future__ import annotations


def test_review_items_generated_for_listing_and_image(client, product_id, wait_task):
    """生成文案与图片后，必须自动产出对应的风险检查项。"""
    # 自给数据：确保测试可独立运行
    lt = client.post("/api/listings/tasks", json={
        "product_id": product_id, "platform": "amazon", "markets": ["DE"]}).json()[0]
    wait_task("listing", lt["id"])
    it = client.post("/api/images/tasks", json={
        "product_id": product_id, "image_type": "main", "market": "DE",
        "aspect_ratio": "1:1", "count": 1}).json()["id"]
    wait_task("image", it)

    reviews = client.get("/api/reviews", params={"product_id": product_id}).json()
    assert len(reviews) > 0

    targets = {r["target_type"] for r in reviews}
    assert {"listing", "image"} <= targets

    # 模拟内容必须被标记为高风险，避免误发布
    sim = [r for r in reviews if r["rule_code"] in ("simulated_content", "simulated_image")]
    assert len(sim) > 0
    assert all(r["level"] == "high" for r in sim)

    # 每项必须包含等级/原因/位置/修改建议
    for r in reviews:
        assert r["level"] in ("high", "medium", "low", "info")
        assert r["reason"] and r["suggestion"]

    # 无法自动判定的项必须标记需人工核实
    manual = [r for r in reviews if r["needs_manual"]]
    assert len(manual) > 0


def test_review_status_transition(client, product_id):
    reviews = client.get("/api/reviews", params={"product_id": product_id, "status": "open"}).json()
    target = reviews[0]
    r = client.patch(f"/api/reviews/{target['id']}", json={"status": "resolved"})
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"

    summary = client.get("/api/reviews/summary").json()
    assert summary["total"] >= 0


def test_review_summary_counts(client):
    s = client.get("/api/reviews/summary").json()
    assert {"total", "high", "medium", "low", "info", "needs_manual"} <= set(s)


def test_export_without_api_key(client, product_id):
    """无 API Key 时导出必须仍然可用。"""
    for t in ("listing_csv", "listing_xlsx", "images_zip", "full_package"):
        payload = {"type": t, "product_id": product_id}
        r = client.post("/api/exports", json=payload)
        assert r.status_code == 200, f"{t}: {r.text}"
        task = r.json()
        assert task["status"] == "completed", f"{t} 未成功：{task}"
        if t != "full_package":
            assert task["file_size"] >= 0

    exports = client.get("/api/exports").json()
    assert len(exports) >= 4
    for e in exports:
        if e["status"] == "completed":
            assert e["download_url"].startswith("/api/files/export/")


def test_export_download_works(client, product_id):
    r = client.post("/api/exports", json={"type": "listing_csv", "product_id": product_id})
    e = r.json()
    if e["status"] != "completed":
        return
    dl = client.get(e["download_url"])
    assert dl.status_code == 200
    assert dl.content


def test_export_csv_prevents_formula_injection(client, product_id):
    """导出的 CSV 中危险前缀必须被转义。"""
    r = client.post("/api/exports", json={"type": "listing_csv", "product_id": product_id})
    e = r.json()
    if e["status"] != "completed":
        return
    text = client.get(e["download_url"]).text
    # 不应存在以 =/+/-/@ 开头的未转义单元格（首字符为引号或普通文本）
    for line in text.splitlines():
        for cell in line.split(","):
            cell = cell.strip()
            if len(cell) > 1 and cell[0] in "=+-@":
                assert False, f"检测到未转义的公式单元格：{cell[:20]}"


def test_full_package_contains_expected_content(client, product_id):
    import io
    import zipfile

    r = client.post("/api/exports", json={"type": "full_package", "product_id": product_id})
    e = r.json()
    assert e["status"] == "completed", e
    content = client.get(e["download_url"]).content
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = zf.namelist()
    assert any("01_product_facts" in n for n in names)
    assert any("02_listings" in n for n in names)
    assert any("03_seo_keywords" in n for n in names)
    assert any("05_review_report" in n for n in names)
    assert any(n.startswith("04_images/") for n in names)


def test_settings_masks_api_key(client):
    r = client.put("/api/settings", json={
        "text_api_key": "sk-super-secret-key-123456",
        "image_api_key": "sk-image-secret-abcdef",
        "text_api_base": "https://example.invalid/v1",
        "text_model": "gpt-4o-mini"})
    assert r.status_code == 200, r.text
    data = r.json()
    # 明文密钥绝不能出现在响应中
    assert "sk-super-secret-key-123456" not in str(data)
    assert "sk-image-secret-abcdef" not in str(data)
    assert data["text_configured"] is True
    assert data["text_api_key_masked"] != ""
    assert "*" in data["text_api_key_masked"]


def test_settings_cost_log_does_not_leak_key(client):
    logs = client.get("/api/settings/cost-logs").json()
    for log in logs:
        assert "sk-super-secret" not in str(log["error"])


def test_settings_reset_to_simulated(client):
    """清空配置回到模拟模式，便于后续测试不受污染。"""
    r = client.put("/api/settings", json={
        "text_api_base": " ", "text_api_key": " ",
        "image_api_base": " ", "image_api_key": " "})
    assert r.status_code == 200


def test_rules_crud_and_default_seeded(client):
    rules = client.get("/api/rules").json()
    assert len(rules) > 0
    # 内置规则必须标记需核实，不能宣称绝对合规
    assert any(r["needs_verify"] for r in rules)

    r = client.post("/api/rules", json={
        "platform": "amazon", "market": "*", "category": "*",
        "rule_type": "text", "code": "test_rule_1", "level": "high",
        "description": "测试规则", "suggestion": "请修改"})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]

    r = client.patch(f"/api/rules/{rid}", json={
        "platform": "amazon", "market": "*", "category": "*",
        "rule_type": "text", "code": "test_rule_1", "level": "low",
        "description": "测试规则已更新", "suggestion": "已更新"})
    assert r.status_code == 200
    assert r.json()["level"] == "low"

    assert client.delete(f"/api/rules/{rid}").status_code == 200


def test_file_path_traversal_blocked(client):
    """导出下载必须防止路径穿越。"""
    r = client.get("/api/files/export/1")
    assert r.status_code in (200, 404, 410)

    # 非法存储路径
    from app.security import safe_join
    from pathlib import Path
    try:
        safe_join(Path("/tmp/base"), "../../../etc/passwd")
        assert False, "路径穿越未被拦截"
    except ValueError:
        pass


def test_csv_safe_escapes_dangerous_prefix():
    from app.security import csv_safe
    assert csv_safe("=SUM(A1)").startswith("'=")
    assert csv_safe("@import").startswith("'@")
    assert csv_safe("normal text") == "normal text"


def test_task_overview_endpoint(client):
    r = client.get("/api/tasks/overview")
    assert r.status_code == 200
    data = r.json()
    assert "listing_tasks" in data and "image_tasks" in data
    assert "today_spend_usd" in data


def test_demo_seed_endpoint(client):
    r = client.post("/api/demo/seed")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    products = client.get("/api/products").json()
    assert any(p["is_demo"] for p in products)
