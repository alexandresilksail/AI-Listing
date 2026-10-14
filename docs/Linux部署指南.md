# Linux 服务器部署指南

> 适用：Ubuntu 22.04 / Debian 12 / CentOS Stream 9 等 systemd 发行版。

## 一、方案选择

| 方案 | 适用场景 | 命令复杂度 |
|------|---------|-----------|
| **Docker Compose**（推荐） | 大多数场景，隔离干净 | 低 |
| 裸机 + systemd + Nginx | 需要直接控制进程、已有 Nginx | 中 |

## 二、Docker Compose 部署（推荐）

### 1. 安装 Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
docker --version
docker compose version
```

### 2. 获取代码并配置

```bash
git clone <你的仓库地址> polylisting-ai
cd polylisting-ai
cp .env.example .env
vim .env        # 按需填写模型 API 与预算（不填也能跑，进入模拟模式）
```

生产环境必须修改：

```ini
PL_DATABASE_URL=postgresql+psycopg://polylisting:<强密码>@db:5432/polylisting
PL_CORS_ORIGINS=https://your-domain.com
PL_DAILY_BUDGET_USD=20
```

### 3. 构建前端产物

前端以静态文件挂载到 Nginx：

```bash
cd frontend
npm install
npm run build      # 产出 frontend/dist
cd ..
```

> `docker-compose.yml` 把 `./frontend/dist` 只读挂载为 Nginx 根，因此**前端代码更新后需重新 build**。

### 4. 启动

```bash
docker compose up -d --build
docker compose logs -f backend
curl http://127.0.0.1:8080/api/health
# {"status":"ok","app":"PolyListing AI","text_configured":false,"image_configured":false}
```

访问 `http://<服务器IP>:8080`。

### 5. 常用运维

```bash
docker compose ps                 # 查看状态
docker compose restart backend
docker compose down               # 停止（数据保留在卷 backend_data）
docker compose logs --tail=100 backend
```

数据卷：`docker volume inspect polylisting-ai_backend_data`，备份该卷或容器内 `/app/data` 即可备份全部业务数据。

## 三、裸机部署（systemd + Nginx）

### 1. 依赖

```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv python3-pip nginx \
    libjpeg-turbo8 zlib1g supervisor
```

### 2. 后端

```bash
sudo mkdir -p /opt/polylisting
sudo chown $USER:$USER /opt/polylisting
cp -r backend frontend demo docs scripts /opt/polylisting/
cd /opt/polylisting/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

创建 `/etc/systemd/system/polylisting.service`：

```ini
[Unit]
Description=PolyListing AI Backend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/polylisting/backend
Environment="PL_DATA_DIR=/opt/polylisting/data"
Environment="PL_DATABASE_URL=sqlite:////opt/polylisting/data/polylisting.db"
EnvironmentFile=-/opt/polylisting/.env
ExecStart=/opt/polylisting/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo mkdir -p /opt/polylisting/data && sudo chown www-data:www-data /opt/polylisting/data
sudo systemctl daemon-reload
sudo systemctl enable --now polylisting
systemctl status polylisting
```

### 3. 前端与 Nginx

```bash
cd /opt/polylisting/frontend
npm install && npm run build
sudo cp -r dist /var/www/polylisting
sudo cp /opt/polylisting/deploy/nginx.conf /etc/nginx/conf.d/polylisting.conf
```

裸机部署时把 nginx 配置里的 `proxy_pass http://backend:8000;` 改成 `proxy_pass http://127.0.0.1:8000;`，并调整 `root` 路径为 `/var/www/polylisting;`。

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 4. HTTPS（可选）

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## 四、切换到 PostgreSQL（生产建议）

```bash
sudo apt install -y postgresql
sudo -u postgres psql -c "CREATE USER polylisting WITH PASSWORD '<强密码>';"
sudo -u postgres psql -c "CREATE DATABASE polylisting OWNER polylisting;"
pip install psycopg[binary]
```

设置 `PL_DATABASE_URL=postgresql+psycopg://polylisting:<密码>@127.0.0.1:5432/polylisting`，重启服务：

```bash
cd /opt/polylisting/backend
source .venv/bin/activate
alembic upgrade head     # 生产推荐使用迁移而非 create_all
```

## 五、安全加固清单

- [ ] `.env` 与 `data/runtime_settings.json` 权限 600，**不进版本库**（`.gitignore` 已排除）
- [ ] `PL_API_TOKEN` 设置并与反向代理层鉴权配合
- [ ] 防火墙只开放 80/443，禁止 8000 端口对外（`ufw allow 80,443/tcp`）
- [ ] 定期备份 `data/` 或 PostgreSQL
- [ ] 生产 `PL_CORS_ORIGINS` 只填写自己的域名，不要用 `*`
- [ ] 上传目录与 Nginx `client_max_body_size` 保持一致（示例为 30m）

## 六、升级

```bash
git pull
cd frontend && npm install && npm run build && cd ..
sudo systemctl restart polylisting
sudo nginx -t && sudo systemctl reload nginx
```
