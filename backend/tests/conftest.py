"""测试固件：隔离临时数据库与存储目录，统一 API 令牌鉴权。

必须在导入任何 app 模块之前设置 PL_DATA_DIR / PL_DATABASE_URL，
因为 config 模块在导入时就会计算这些路径常量。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

_tmp_root = Path(tempfile.mkdtemp(prefix="polylisting_test_"))
_data_dir = _tmp_root / "data"
_data_dir.mkdir(parents=True, exist_ok=True)

TEST_API_TOKEN = "test-secret-token-123456"

os.environ["PL_DATA_DIR"] = str(_data_dir)
os.environ["PL_DATABASE_URL"] = f"sqlite:///{(_data_dir / 'test.db').as_posix()}"
os.environ["PL_TEXT_API_BASE"] = ""
os.environ["PL_TEXT_API_KEY"] = ""
os.environ["PL_IMAGE_API_BASE"] = ""
os.environ["PL_IMAGE_API_KEY"] = ""
# 测试环境配置 API 令牌：验证全局鉴权生效（未授权请求必须被拒绝）
os.environ["PL_API_TOKEN"] = TEST_API_TOKEN
# 测试环境为 development（不触发生产 fail-fast）
os.environ["PL_ENV"] = "development"

import pytest  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

TOKEN_HEADERS = {"X-API-Token": TEST_API_TOKEN}


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    init_db()
    yield


@pytest.fixture(scope="session")
def client():
    """带令牌的测试客户端（模拟已授权前端）。"""
    from fastapi.testclient import TestClient

    with TestClient(app, headers=TOKEN_HEADERS) as c:
        yield c


@pytest.fixture(scope="session")
def anon_client():
    """不带令牌的测试客户端（用于验证未授权请求被拒绝）。"""
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def product_id(client):
    """创建测试商品（中文详情用于参数提取测试）。"""
    resp = client.post("/api/products", json={
        "sku": "TEST-SKU-001",
        "name": "Test Insulated Sport Bottle 500ml",
        "brand": "TestBrand",
        "model": "T-500",
        "category": "outdoor",
        "source_text": ("便携式运动保温水壶。材质：304 不锈钢。尺寸：高 24cm。颜色：黑色。"
                        "重量：300g。容量：500ml。适用人群：运动人群。"
                        "适用场景：健身房、户外徒步。包装清单：水壶 x1、杯刷 x1。"
                        "注意事项：请勿放入微波炉。"),
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


@pytest.fixture(scope="session")
def wait_task(client):
    """轮询等待异步队列任务结束，返回最终任务状态。"""

    def _wait(kind: str, task_id: int, timeout: int = 60) -> dict:
        url = f"/api/{'listings' if kind == 'listing' else 'images'}/tasks/{task_id}"
        deadline = time.time() + timeout
        last: dict = {}
        while time.time() < deadline:
            r = client.get(url)
            assert r.status_code == 200, r.text
            last = r.json()
            if last.get("status") in ("completed", "failed", "partial"):
                return last
            time.sleep(0.2)
        raise AssertionError(f"任务 {kind}#{task_id} 在 {timeout}s 内未结束：{last}")

    return _wait


@pytest.fixture
def settings_env(monkeypatch):
    """临时修改 PL_ 环境变量并清空 settings 缓存（全局 fixture）。

    用法：settings_env(text_api_key="sk-x", daily_budget_usd=5)
    退出时自动恢复环境变量与缓存。
    """
    from app.config import get_settings

    def _set(**kw):
        for k, v in kw.items():
            monkeypatch.setenv(f"PL_{k.upper()}", str(v))
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()
