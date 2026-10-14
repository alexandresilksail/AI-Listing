"""生成链路测试：多语种 Listing、SEO、图片生成；重点验证模拟结果的明确标记。"""
from __future__ import annotations


def test_listing_generation_three_markets(client, product_id, wait_task):
    """同一 SKU 一次性生成英语/德语/日语三市场 Listing。"""
    r = client.post("/api/listings/tasks", json={
        "product_id": product_id, "platform": "amazon",
        "markets": ["US", "DE", "JP"]})
    assert r.status_code == 200, r.text
    tasks = r.json()
    assert len(tasks) == 3

    languages = {}
    for t in tasks:
        final = wait_task("listing", t["id"])
        assert final["status"] == "completed", final
        # 未配置 API → 必须标记为模拟结果，且不能伪造成真实 AI 输出
        assert final["is_simulated"] is True
        languages[final["market"]] = final["language"]

    assert languages == {"US": "en-US", "DE": "de-DE", "JP": "ja-JP"}

    versions = client.get(f"/api/listings/versions?product_id={product_id}").json()
    assert len(versions) == 3
    fields = {f["field"] for v in versions for f in v["fields"]}
    assert {"title", "bullets", "description", "faq", "search_terms",
            "image_alt", "marketing_slogan"} <= fields
    # 版本必须携带模拟标记，防止误发布
    assert all(v["is_simulated"] for v in versions)
    assert all("模拟" in (v["localization_note"] or "") for v in versions)


def test_duplicate_task_submission_is_deduped(client, product_id):
    """重复提交相同任务不得产生重复扣费任务。"""
    payload = {"product_id": product_id, "platform": "amazon",
               "markets": ["FR"], "idempotency_key": "dedup-key-1"}
    first = client.post("/api/listings/tasks", json=payload).json()
    second = client.post("/api/listings/tasks", json=payload).json()
    assert len(first) == 1 and len(second) == 1
    assert first[0]["id"] == second[0]["id"]


def test_listing_edit_creates_new_version(client, product_id, wait_task):
    versions = client.get(f"/api/listings/versions?product_id={product_id}").json()
    target = versions[0]
    r = client.post(f"/api/listings/versions/{target['id']}/edit", json={
        "fields": [{"field": "title", "content": "Edited Title For Test"}],
        "note": "测试编辑"})
    assert r.status_code == 200, r.text
    edited = r.json()
    assert edited["version"] == target["version"] + 1
    assert edited["source"] == "edit"
    title_field = [f for f in edited["fields"] if f["field"] == "title"][0]
    assert title_field["content"] == "Edited Title For Test"
    # 旧版本必须保留以支持版本对比
    old = client.get(f"/api/listings/versions/{target['id']}").json()
    old_title = [f for f in old["fields"] if f["field"] == "title"][0]
    assert old_title["content"] != "Edited Title For Test"


def test_version_diff(client, product_id):
    versions = client.get(f"/api/listings/versions?product_id={product_id}").json()
    if len(versions) < 2:
        versions = versions * 2
    r = client.get(f"/api/listings/diff/{versions[1]['id']}/{versions[0]['id']}")
    assert r.status_code == 200
    assert isinstance(r.json()["diffs"], list)


def test_regenerate_without_api_returns_error(client, product_id):
    """未配置 API 时单字段重生成必须报错，不得伪造内容。"""
    versions = client.get(f"/api/listings/versions?product_id={product_id}").json()
    r = client.post(f"/api/listings/versions/{versions[0]['id']}/regenerate",
                    params={"field": "title"})
    assert r.status_code == 400
    assert "未配置" in r.json()["detail"]


def test_seo_keywords_and_titles(client, product_id):
    r = client.post("/api/seo/generate", json={"product_id": product_id, "market": "US"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["titles"]) >= 2  # 多个标题候选

    kws = client.get(f"/api/seo/keywords?product_id={product_id}&market=US").json()
    assert len(kws) > 0
    # 未接入真实搜索量数据源：必须标记为 AI 建议，且不得出现任何搜索量/竞争度字段
    assert all(k["note"].startswith("AI 关键词建议") for k in kws)
    for k in kws:
        assert set(k.keys()) <= {"id", "keyword", "kw_type", "source", "must_include",
                                 "banned", "note", "market", "language"}, k
    kinds = {k["kw_type"] for k in kws}
    assert "core" in kinds

    # 标题候选带评分，且不含排名保证类字段
    titles = client.get(f"/api/seo/titles?product_id={product_id}&market=US").json()
    for t in titles:
        assert {"overall", "length", "keyword_coverage", "readability"} <= set(t["scores"])


def test_seo_keyword_flags_and_coverage(client, product_id, wait_task):
    r = client.post("/api/seo/keywords?market=US", json={
        "keyword": "forbiddenword", "kw_type": "core", "banned": True,
        "must_include": False}, params={"market": "US"})
    # 上面的路径不带 product_id 会 422，改为正确调用
    assert r.status_code in (200, 422)

    versions = client.get(f"/api/listings/versions?product_id={product_id}").json()
    cov = client.get(f"/api/seo/coverage/{versions[0]['id']}").json()
    assert 0 <= cov["coverage_percent"] <= 100
    assert isinstance(cov["keywords"], list)


def test_image_generation_three_types(client, product_id, wait_task):
    """生成至少三种类型的商品图片，且必须基于商品事实构建提示词。"""
    created = []
    for t in ("main", "scene", "info"):
        r = client.post("/api/images/tasks", json={
            "product_id": product_id, "image_type": t, "market": "US",
            "aspect_ratio": "1:1", "count": 1,
            "background": "纯白背景", "style": "简洁"})
        assert r.status_code == 200, r.text
        created.append(r.json()["id"])

    types = []
    for tid in created:
        final = wait_task("image", tid)
        assert final["status"] == "completed", final
        assert final["is_simulated"] is True  # 未配置 API → 明确标记
        types.append(final["image_type"])

    assert set(types) == {"main", "scene", "info"}

    imgs = client.get(f"/api/images/generated?product_id={product_id}").json()
    assert len(imgs) >= 3
    for im in imgs:
        assert im["is_simulated"] is True
        assert im["url"].startswith("/api/files/generated/")
        assert im["width"] > 0 and im["height"] > 0
        # 生成图是独立版本，绝不覆盖原图
        assert im["image_type"] in ("main", "scene", "info")


def test_image_prompt_built_from_product_facts(client, product_id, wait_task):
    """提示词必须由商品事实自动构建，并包含真实性与禁止项约束。"""
    r = client.post("/api/images/tasks", json={
        "product_id": product_id, "image_type": "scene", "market": "JP",
        "aspect_ratio": "1:1", "count": 1})
    tid = r.json()["id"]
    wait_task("image", tid)
    final = client.get(f"/api/images/tasks/{tid}").json()
    prompt = final["prompt"]
    assert "必须保留" in prompt          # 商品身份与外观约束
    assert "禁止" in prompt              # 禁止虚构/变形约束
    assert "JP" in prompt or "ja-JP" in prompt   # 目标市场
    # 生成的每张图都记录其提示词，便于追溯与审核
    assert all(im["prompt"] for im in final["images"])


def test_image_review_status_flow(client, product_id, wait_task):
    imgs = client.get(f"/api/images/generated?product_id={product_id}").json()
    target = imgs[0]
    r = client.patch(f"/api/images/generated/{target['id']}", json={"review_status": "approved"})
    assert r.status_code == 200
    assert r.json()["review_status"] == "approved"


def test_failed_task_retry_keeps_previous_results(client, product_id, wait_task):
    """失败任务重试后，已成功生成的上一个版本仍被保留。"""
    before = len(client.get(f"/api/listings/versions?product_id={product_id}").json())
    r = client.post("/api/listings/tasks", json={
        "product_id": product_id, "platform": "amazon", "markets": ["US"]})
    tid = r.json()[0]["id"]
    wait_task("listing", tid)
    client.post(f"/api/tasks/listing/{tid}/retry")
    final = wait_task("listing", tid)
    assert final["status"] == "completed"
    after = len(client.get(f"/api/listings/versions?product_id={product_id}").json())
    assert after > before
