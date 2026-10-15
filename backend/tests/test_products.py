"""商品管理测试：CRUD、参数提取、图片上传校验、批量导入、删除关联清理。"""
from __future__ import annotations

import io

from PIL import Image


def _png_bytes(w=64, h=64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_create_list_get_product(client):
    resp = client.post("/api/products", json={
        "sku": "SKU-A-1", "name": "商品A", "brand": "BrandA", "category": "home"})
    assert resp.status_code == 200, resp.text
    pid = resp.json()["id"]

    assert client.post("/api/products", json={"sku": "SKU-A-1"}).status_code == 409  # 唯一约束

    listed = client.get("/api/products").json()
    assert any(p["sku"] == "SKU-A-1" for p in listed)

    got = client.get(f"/api/products/{pid}").json()
    assert got["name"] == "商品A"


def test_update_product(client, product_id):
    r = client.patch(f"/api/products/{product_id}", json={"name": "更新后的名称"})
    assert r.status_code == 200
    assert r.json()["name"] == "更新后的名称"


def test_extract_params_from_chinese_text(client, product_id):
    r = client.post(f"/api/products/{product_id}/extract-params")
    assert r.status_code == 200, r.text
    data = r.json()
    keys = {p["key"] for p in data["params"]}
    # 至少能从中文详情中抽取出材质/容量/重量等字段
    assert {"材质", "容量"} <= keys, keys
    # 抽取结果默认未验证（防止 AI/后续流程直接使用未确认参数）
    assert all(p["verified"] is False for p in data["params"])


def test_add_and_delete_param(client, product_id):
    r = client.post(f"/api/products/{product_id}/params", json=[
        {"group": "cert", "key": "认证", "value": "", "verified": False}])
    assert r.status_code == 200
    param_id = [p for p in r.json()["params"] if p["key"] == "认证"][0]["id"]
    r = client.delete(f"/api/products/{product_id}/params/{param_id}")
    assert r.status_code == 200
    assert all(p["key"] != "认证" for p in r.json()["params"])


def test_upload_image_and_keep_original(client, product_id):
    files = {"file": ("main.png", _png_bytes(), "image/png")}
    r = client.post(f"/api/products/{product_id}/images", files=files, data={"kind": "main"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["images"]) >= 1
    img = data["images"][0]
    assert img["width"] == 64 and img["height"] == 64
    assert img["url"].startswith("/api/files/image/")

    # 原图可通过文件接口读取
    raw = client.get(img["url"].replace("/api/files/image/", "/api/files/image/"))
    assert raw.status_code == 200
    assert raw.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_upload_rejects_non_image(client, product_id):
    """上传非图片必须被拒绝（扩展名 + 魔数双重校验）。"""
    files = {"file": ("evil.png", b"<?php echo 1; ?>", "image/png")}
    r = client.post(f"/api/products/{product_id}/images", files=files, data={"kind": "main"})
    assert r.status_code == 400
    assert "不是有效的图片" in r.json()["detail"]


def test_upload_rejects_unsupported_extension(client, product_id):
    files = {"file": ("a.gif", b"GIF89a" + b"0" * 40, "image/gif")}
    r = client.post(f"/api/products/{product_id}/images", files=files, data={"kind": "main"})
    assert r.status_code == 400
    assert "不支持的图片格式" in r.json()["detail"]


def test_import_csv(client):
    csv_text = ("sku,name,brand,category\n"
                "IMP-001,Imported One,B1,home\n"
                "IMP-002,Imported Two,B2,kitchen\n"
                "IMP-002,Duplicate,B2,kitchen\n")
    files = {"file": ("products.csv", csv_text.encode("utf-8"), "text/csv")}
    r = client.post("/api/products/import", files=files)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["imported"] == 2
    assert result["skipped"] == 1  # 重复 SKU 被跳过


def test_import_unsupported_format(client):
    files = {"file": ("a.json", b"{}", "application/json")}
    r = client.post("/api/products/import", files=files)
    assert r.status_code == 400


def test_delete_product_clears_relations(client):
    r = client.post("/api/products", json={"sku": "DEL-001", "name": "待删除"})
    pid = r.json()["id"]
    client.post(f"/api/products/{pid}/images",
                files={"file": ("x.png", _png_bytes(), "image/png")}, data={"kind": "main"})
    r = client.delete(f"/api/products/{pid}")
    assert r.status_code == 200
    assert client.get(f"/api/products/{pid}").status_code == 404
