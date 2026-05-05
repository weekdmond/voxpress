# VoxPress 部署方案

> 目标形态：单台 ECS 同时跑 **API + Worker + Postgres + Dashboard 静态站**，OSS 走同 region 内网，DashScope 走公网。
> 目标吞吐：稳态 2000+ 条/天，贴合你 400 条/天的日常用量。
> 预期月费：**硬件 ~¥230 + DashScope 按量（400 条/天约 ¥1400）**，详见第 13 节。
>
> 前端（dashboard）和后端是**两个仓库**：后端是本仓库 `voxpress-api`（FastAPI + Worker），前端是同级目录的 `voxpress/`（Vite + React + TypeScript）。部署方式是：**后端 git clone 到 ECS 跑起来，前端本地构建后把 `dist/` 上传到 ECS，Nginx 同域分发**（`/api/*` → FastAPI，其余 → 静态文件）。

---

## 0. 当前生产实际拓扑（速查）

> 本节是**线上现状速查**，与下面 §1–§9 描述的"目标方案"不完全一致。接手或排查时**先看本节**对齐事实，再查具体步骤。最近一次校对：2026-05-05。

### 0.1 主机清单

| 角色 | hostname | 公网 EIP | 内网 IP | ssh-relay 入口 |
|---|---|---|---|---|
| App（API + Worker + Nginx + Dashboard 静态） | `speechfolio`（曾用 `voxpress-20260423`） | `47.237.81.215` | `192.168.233.81` | `ssh-relay 47.237.81.215` |
| PG（PostgreSQL 16） | `postgres-20260424` | `43.98.194.178` | `192.168.233.52` | `ssh-relay 43.98.194.178` |
| 公网入口 | 阿里云 SLB（实例 ID 待补） | — | — | 阿里云控制台 |

**对外域名**：`https://app.speechfolio.com/`（Dashboard + `/api/*`）。SLB 上做 SSL 卸载，再把请求转到 App ECS 的 `:8080`。

历史 EIP（已下线但 App 机 nginx `server_name` 仍残留）：`43.98.200.159`、`43.98.204.138`。维护时可清掉。

### 0.2 关键路径与服务

**App 机（`47.237.81.215`）**：

- 代码：`/home/work/app/voxpress-api`（**注意**：不是 §6.1 模板里的 `/home/voxpress/voxpress-api`，运行账号是 `work`）
- 环境：`/home/work/app/voxpress-api/.env`（auto-generated，文件头有时间戳注释）
- 日志：`/var/voxpress/logs/{api,worker}.log` + `journalctl -u voxpress-{api,worker}`
- 媒体缓存：`/var/voxpress/{audio,video}`
- systemd 单元：`voxpress-api.service`、`voxpress-worker.service`
- Nginx：listen `0.0.0.0:8080`（**不是** 80/443），配置 `/etc/nginx/sites-available/voxpress`

**PG 机（`43.98.194.178`）**：

- 数据：`/var/lib/postgresql/16/main`
- 日志：`/var/log/postgresql/postgresql-16-main.log`
- 监听：`127.0.0.1:5432` + `192.168.233.52:5432`（不监听公网）
- 数据库：`voxpress`，所属角色 `voxpress`
- 客户端 ACL **三层**（都要放行 App 子网）：
  - `pg_hba.conf`: `host voxpress voxpress 192.168.233.0/24 scram-sha-256`
  - `ufw`: `5432/tcp ALLOW IN 192.168.233.0/24`
  - 阿里云安全组：入方向 5432 限 VPC 内

### 0.3 公网入口（SLB 层，待补全）

线上请求路径推断：

```
浏览器 → 阿里云 SLB(443/80, SSL 终结) → App ECS:8080(nginx) → 127.0.0.1:8787(uvicorn)
```

App 机本身**没有 listen 80/443**，也**没有 Let's Encrypt 证书目录**（`/etc/letsencrypt/live` 不存在），所以前面必有 SLB（或类似负载均衡）做 443→8080 转发与 SSL 卸载。

接手时到阿里云控制台核对并回写本节：

- SLB 实例 ID / 名称
- 监听规则（80→8080、443→8080 + SSL 证书）
- 后端服务器组挂的 ECS 实例 ID 是否就是当前 App 机
- 健康检查路径（建议 `GET /api/health`，期望 200）
- SSL 证书有效期与续期方式

### 0.4 ssh-relay 工具（团队约定）

`ssh-relay` 是本地脚本（`~/util/ssh-relay.sh`），传 IPv4 时等价于：

```bash
ssh -i ~/.ssh/tflyer-sg-inter-ssh-key-423.pem root@<ip>
```

命名别名（`ssh-relay hb` / `ssh-relay tf` 等）对应不同 key，看脚本即可。

### 0.5 与 §1–§9 目标方案的主要差异

| 项 | §1–§9 文档目标 | 当前线上 |
|---|---|---|
| PG 拓扑 | 同机本地 unix socket | 拆机，跨内网走 5432 |
| App 用户/路径 | `voxpress`/`/home/voxpress/voxpress-api` | `work`/`/home/work/app/voxpress-api` |
| Nginx 入口 | 直接 listen 80/443 + Let's Encrypt | listen 8080，SLB 在前做 SSL 卸载 |
| 客户端 DB ACL | 默认 localhost | pg_hba + ufw + 安全组 三层放行子网 |

故障排查标准顺序见 §10.6；ECS 重建/换 IP 的回灌清单见 §10.7；本次双机拓扑的踩坑总结见 §12 第 14–17 条。

---

## 1. 架构与资源清单

> **注**：本节是**全新部署的目标方案**（单机自托管全部组件）。当前线上实际是 §0 描述的双机拆分拓扑，请以 §0 为准。

```
              ┌───────── 浏览器 ─────────┐
              │ https://voxpress.yourhost │
              └─────────────┬─────────────┘
                            │ 443
                    ┌───────▼────────┐
                    │     Nginx      │
                    │                │
                    │  /  → dist/    │  ← Dashboard 静态产物
                    │  /api → :8787  │  ← FastAPI 反代（含 SSE）
                    └───────┬────────┘
                            │ 127.0.0.1:8787
┌──────────────────────────▼────────────────────────┐
│ ECS 4C8G Ubuntu 24.04                             │
│ ┌────────────┐  ┌────────────┐  ┌───────────────┐ │
│ │ voxpress-  │  │ voxpress-  │  │ PostgreSQL 16 │ │
│ │ api        │  │ worker     │  │ (本机 unix sock)│ │
│ └────────────┘  └─────┬──────┘  └───────────────┘ │
│ /var/www/voxpress-web (Dashboard dist/)           │
└──────────────────────│────────────────────────────┘
                       │                 ▲
            ┌──────────▼──────┐   ┌──────┴──────┐
            │ DashScope 公网  │   │  OSS 内网    │
            │  (同 region)    │   │  (同 region) │
            └─────────────────┘   └─────────────┘
                       │
                       ▼
                  抖音公网 (下载视频)
```

**资源清单**（默认阿里云杭州 region `cn-hangzhou`）：

| 资源 | 规格 | 月费 | 说明 |
|---|---|---|---|
| ECS | 通用型 g7，4 vCPU / 8 GB / ESSD PL0 80 GB | ~¥170 | 按量带宽，峰值 50 Mbps |
| 弹性公网 IP | 按量付费 | ~¥15 | 入方向（下抖音视频）免费 |
| OSS Bucket | 标准存储，私有读 | ¥12–20 | 同 region 内网 endpoint，0 流量费 |
| RAM 用户 | AK/SK 只授该 bucket 权限 | 0 | 不要用主账号 AK |
| 域名 + SSL | 可选 | ¥30–100/年 | Let's Encrypt 免费 |
| **硬件合计** |  | **~¥220/月** | |
| DashScope | 按调用计费 | ~¥1400/月 | 400 条/天时的预估 |

**为什么不用 RDS**：4C8G 同机跑 PG 16 完全不吃力，早期也方便调试；等单日>2000 条或要做只读副本时再拆到 RDS 基础版（¥150/月起）。

---

## 2. 前置准备（本地把这些备齐再开 ECS）

1. **阿里云账号**，已完成实名认证。
2. **DashScope API Key**（<https://dashscope.console.aliyun.com>）：
   - 开通服务、充值 ¥200 做启动资金
   - **在"模型限流"里提工单**申请把 `qwen3.6-plus` RPM 提到 300+、`qwen3-asr-flash-filetrans` 并发任务提到 20+；默认额度跑不起来 `organize_concurrency=8` 的批量
3. **抖音 cookie.txt**：用浏览器插件（Get cookies.txt LOCALLY）从 `douyin.com` 域导出，保留 `sessionid / ttwid / passport_csrf_token` 等核心字段
4. **域名**（可选但强烈建议）：指向后面要分配的 EIP。用 IP 直连可以跑，但没有 HTTPS 前端 CORS 会很别扭
5. **本地 SSH 密钥**：`ssh-keygen -t ed25519` 生成，上传公钥到阿里云"密钥对"

---

## 3. 云资源创建（控制台一把过）

### 3.1 VPC 与安全组
- VPC：默认 VPC 即可
- 交换机：选和 OSS 同 region 的可用区
- **安全组入方向**：
  - TCP 22：来源限你当前出口 IP（`curl ifconfig.me` 看一下）
  - TCP 80、443：0.0.0.0/0
  - **不要开 8787**（FastAPI 直连端口）、**不要开 5432**（Postgres）

### 3.2 ECS
- 镜像：Ubuntu 24.04 LTS 64 位（自带 Python 3.12）
- 规格：`ecs.g7.xlarge`（4C8G）
- 系统盘：ESSD PL0，80 GB
- 公网：分配 EIP，按量带宽，峰值 50 Mbps
- 登录：SSH 密钥对
- 启动后记下公网 IP、内网 IP

### 3.3 OSS
- Bucket 名：例如 `voxpress-media-prod`
- region：和 ECS 同 region
- 读写权限：私有
- 版本控制：关闭
- 服务端加密：OSS 完全托管
- **把 Bucket 内网 endpoint 记下来**，形如 `oss-cn-hangzhou-internal.aliyuncs.com`

### 3.4 RAM 子账号
- 创建 RAM 用户 `voxpress-deployer`，开启 OpenAPI 调用
- 授权仅允许：自定义策略把 `oss:*` 的 Resource 限死到上面那个 bucket
- 记下 AccessKey ID 和 Secret

### 3.5 域名解析（可选）
- 在域名服务商控制台加一条 A 记录：`voxpress.yourdomain.com` → ECS EIP
- 等 DNS 生效（5–30 分钟）

---

## 4. 服务器初始化

SSH 上去以 root 身份执行：

```bash
# 4.1 系统更新与基础工具
apt update && apt upgrade -y
apt install -y build-essential git curl wget jq unzip ufw \
               ffmpeg \
               python3.12 python3.12-venv python3-pip \
               nginx certbot python3-certbot-nginx \
               postgresql-16 postgresql-contrib-16 \
               tzdata

# 4.2 时区
timedatectl set-timezone Asia/Shanghai

# 4.3 UFW（安全组已经拦了一层，再做一层纵深）
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# 4.4 创建运行账户
useradd -m -s /bin/bash voxpress
mkdir -p /var/voxpress/{audio,video,logs}
chown -R voxpress:voxpress /var/voxpress
```

---

## 5. Postgres 初始化

```bash
# 5.1 切到 postgres 用户创建库和账号
sudo -u postgres psql <<'SQL'
CREATE USER voxpress WITH PASSWORD '替换成强密码';
CREATE DATABASE voxpress OWNER voxpress ENCODING 'UTF8';
\c voxpress
CREATE EXTENSION IF NOT EXISTS pg_trgm;
GRANT ALL PRIVILEGES ON DATABASE voxpress TO voxpress;
SQL
```

**调优 `/etc/postgresql/16/main/postgresql.conf`**（4C8G 推荐值）：

```conf
max_connections = 200
shared_buffers = 2GB
effective_cache_size = 6GB
work_mem = 16MB
maintenance_work_mem = 512MB
wal_buffers = 16MB
checkpoint_completion_target = 0.9
random_page_cost = 1.1       # ESSD 是 SSD
log_min_duration_statement = 500ms
```

`pg_hba.conf` 保持默认的 `local all all peer` 和 `host all all 127.0.0.1/32 scram-sha-256` 即可，不要开公网 5432。

```bash
systemctl restart postgresql
systemctl enable postgresql

# 验证
sudo -u voxpress psql -h 127.0.0.1 -U voxpress -d voxpress -c 'select 1;'
```

---

## 6. 应用部署

### 6.1 拉代码 + 虚拟环境

> **注**：实际线上路径是 `/home/work/app/voxpress-api`，运行账号是 `work`。新机器全新部署可按下方模板，老机器接手以 §0 为准。

```bash
su - voxpress
cd ~
git clone <你的 voxpress-api 仓库 URL> voxpress-api
cd voxpress-api

python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel
pip install -e .   # 或者: pip install -r requirements.txt
```

### 6.2 环境变量文件

`~/voxpress-api/.env`（**600 权限、不要进 git**）：

```dotenv
# ----- 基础 -----
VOXPRESS_DB_URL=postgresql+asyncpg://voxpress:替换成强密码@127.0.0.1/voxpress
VOXPRESS_HOST=127.0.0.1
VOXPRESS_PORT=8787
VOXPRESS_CORS_ORIGINS=https://voxpress.yourdomain.com

# ----- 本地缓存目录（重要：不要放 /tmp）-----
VOXPRESS_AUDIO_DIR=/var/voxpress/audio
VOXPRESS_VIDEO_DIR=/var/voxpress/video

# ----- Pipeline 选 real -----
VOXPRESS_PIPELINE=real

# ----- DashScope -----
VOXPRESS_DASHSCOPE_API_KEY=sk-你的key
VOXPRESS_DASHSCOPE_DEFAULT_LLM_MODEL=qwen3.6-plus
VOXPRESS_DASHSCOPE_DEFAULT_CORRECTOR_MODEL=qwen-turbo
VOXPRESS_DASHSCOPE_DEFAULT_ASR_MODEL=qwen3-asr-flash-filetrans

# ----- 并发（Day 1 用保守值，确认无 429 / 无风控后再放开）-----
VOXPRESS_DOWNLOAD_CONCURRENCY=2
VOXPRESS_TRANSCRIBE_CONCURRENCY=4
VOXPRESS_CORRECT_CONCURRENCY=6
VOXPRESS_ORGANIZE_CONCURRENCY=4
VOXPRESS_SAVE_CONCURRENCY=4

# ----- OSS（同 region 内网 endpoint）-----
VOXPRESS_OSS_REGION=cn-hangzhou
VOXPRESS_OSS_ENDPOINT=oss-cn-hangzhou-internal.aliyuncs.com
VOXPRESS_OSS_BUCKET=voxpress-media-prod
VOXPRESS_OSS_ACCESS_KEY_ID=LTAI...
VOXPRESS_OSS_ACCESS_KEY_SECRET=...
VOXPRESS_OSS_SIGN_EXPIRES_SEC=3600
```

```bash
chmod 600 .env
```

### 6.3 数据库迁移

```bash
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
alembic upgrade head
```

### 6.4 手工冒烟

```bash
uvicorn voxpress.main:app --host 127.0.0.1 --port 8787
# 另一个终端
curl http://127.0.0.1:8787/api/health
# 预期 {"status":"ok","db_ok":true,"dashscope_enabled":true,...}
```

跑通就 `Ctrl+C`，进入 systemd 托管。

---

## 7. systemd 单元

### 7.1 `/etc/systemd/system/voxpress-api.service`

```ini
[Unit]
Description=VoxPress API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=voxpress
Group=voxpress
WorkingDirectory=/home/voxpress/voxpress-api
EnvironmentFile=/home/voxpress/voxpress-api/.env
ExecStart=/home/voxpress/voxpress-api/.venv/bin/uvicorn voxpress.main:app \
          --host 127.0.0.1 --port 8787 --proxy-headers --log-level info
Restart=always
RestartSec=5
StandardOutput=append:/var/voxpress/logs/api.log
StandardError=append:/var/voxpress/logs/api.log

[Install]
WantedBy=multi-user.target
```

### 7.2 `/etc/systemd/system/voxpress-worker.service`

```ini
[Unit]
Description=VoxPress Worker
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=voxpress
Group=voxpress
WorkingDirectory=/home/voxpress/voxpress-api
EnvironmentFile=/home/voxpress/voxpress-api/.env
ExecStart=/home/voxpress/voxpress-api/.venv/bin/python -m voxpress.worker
Restart=always
RestartSec=10
LimitNOFILE=65535
StandardOutput=append:/var/voxpress/logs/worker.log
StandardError=append:/var/voxpress/logs/worker.log

[Install]
WantedBy=multi-user.target
```

启动：

```bash
systemctl daemon-reload
systemctl enable --now voxpress-api voxpress-worker
systemctl status voxpress-api voxpress-worker
journalctl -u voxpress-api -f
```

---

## 8. Dashboard 部署（voxpress 前端仓库）

前端是**另一个仓库**（同级目录 `voxpress/`，Vite + React + TS），部署方式是"**本地构建 → rsync 上传到 ECS `/var/www/voxpress-web/` → Nginx 同域分发**"。

### 8.1 本地构建产物

在**本地开发机**（不是 ECS 上）：

```bash
cd /path/to/voxpress          # 前端仓库根目录
git pull --ff-only
cp .env.example .env.production
```

编辑 `.env.production`：

```dotenv
VITE_API_BASE=https://voxpress.yourdomain.com
VITE_SSE_BASE=https://voxpress.yourdomain.com
VITE_USE_MOCK=false
VITE_ENABLE_TWEAKS=false
```

> **重要**：`VITE_*` 变量是**构建时注入**，不是运行时读。每次改 `.env.production` 都必须重新 `npm run build`，否则上线的还是老值。

```bash
npm ci
npm run build
# 产物在 ./dist/
```

### 8.2 上传到 ECS

```bash
# ECS 上先建目录（第一次部署）
ssh voxpress@<ECS-IP> 'mkdir -p /var/www/voxpress-web'

# 本地推送（rsync 更快，--delete 保证移除旧版本里不再需要的文件）
rsync -avz --delete ./dist/ voxpress@<ECS-IP>:/var/www/voxpress-web/
```

如果 voxpress 账号对 `/var/www/voxpress-web` 没写权限，先在 ECS 上：

```bash
sudo mkdir -p /var/www/voxpress-web
sudo chown -R voxpress:voxpress /var/www/voxpress-web
```

### 8.3 `.env.production` 与生产 CORS 对齐

三处域名/地址必须一致，任何一处不一致都会在浏览器里 CORS 失败或 404：

| 位置 | 值 |
|---|---|
| 前端 `.env.production` 的 `VITE_API_BASE / VITE_SSE_BASE` | `https://voxpress.yourdomain.com` |
| 后端 `.env` 的 `VOXPRESS_CORS_ORIGINS` | `https://voxpress.yourdomain.com` |
| Nginx `server_name` + SSL 证书绑定的域名 | `voxpress.yourdomain.com` |

实际上因为同域部署（Nginx 同时承载前端静态 + `/api` 反代），前端请求 `/api/...` 相对路径本来也能跑；但显式写绝对地址更利于后续做前后端分机部署。

### 8.4 验证

浏览器访问 `https://voxpress.yourdomain.com/`：

- 能看到主界面
- DevTools → Network 里对 `/api/...` 的请求返回 200
- `/api/tasks/stream` 是 `text/event-stream`、`transfer-encoding: chunked`，进度实时更新
- 如果看到界面但数据显示"mock 数据"/固定列表 → `VITE_USE_MOCK` 没改成 `false`，重新构建上传

---

## 9. Nginx + HTTPS

`/etc/nginx/sites-available/voxpress`：

```nginx
server {
    listen 80;
    server_name voxpress.yourdomain.com;

    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2;
    server_name voxpress.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/voxpress.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/voxpress.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 20M;

    # 普通 API
    location /api/ {
        proxy_pass http://127.0.0.1:8787;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;      # LLM 长调用
    }

    # SSE：必须关 buffering 才能实时推
    location /api/tasks/stream {
        proxy_pass http://127.0.0.1:8787;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 24h;
        chunked_transfer_encoding on;
    }

    # 前端静态资源（第 8 节产物）
    root /var/www/voxpress-web;

    # 带内容哈希的静态资源，长缓存 + immutable
    location ~* ^/assets/.+\.(js|css|svg|woff2?|ttf|png|jpg|jpeg|webp|gif)$ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        try_files $uri =404;
    }

    # SPA：任何未命中的路径都回 index.html，让前端路由接管
    location / {
        try_files $uri $uri/ /index.html;
    }

    # index.html 不要缓存，否则发布新版本浏览器还用旧入口
    location = /index.html {
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }
}
```

```bash
ln -s /etc/nginx/sites-available/voxpress /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d voxpress.yourdomain.com --agree-tos -m you@example.com --redirect
```

---

## 9.5 公网入口实际拓扑（SLB → Nginx，线上现状）

§9 描述的是 nginx 直接 listen 80/443 + certbot 续证的"裸 ECS"模式。**线上实际不是这个**：

```
浏览器 → 阿里云 SLB(443/80, SSL 终结) → App ECS:8080(nginx) → 127.0.0.1:8787(uvicorn)
```

因此 App 机的 nginx 配置上：

- `listen 8080;`（不是 `listen 80; listen 443 ssl;`）
- 不需要 `ssl_certificate` 行（SSL 在 SLB 卸载）
- `/etc/letsencrypt/` 目录可能不存在，正常
- `server_name` 保留 `_`（catch-all）+ 当前域名/EIP 即可，**不要再往里塞历史 EIP**（线上现存 `43.98.200.159` `43.98.204.138` 是历史漂移残留，下次维护可清理）
- 阿里云**安全组**要放行 SLB 后端互通到 8080，**不要直接对 0.0.0.0/0 开 8080**

升级或修改 nginx 配置时务必：

1. `nginx -t` 通过后再 reload
2. 改 listen / server_name 后到 SLB 控制台确认健康检查仍 200，否则 SLB 会把这台机器从后端组里摘掉（触发 502）

SLB 配置详情待人工补充到 §0.3。

---

## 10. 日常运维

### 10.1 日志
```bash
journalctl -u voxpress-api -f           # API 实时
journalctl -u voxpress-worker -f        # Worker 实时
tail -f /var/voxpress/logs/*.log        # systemd 同时落盘
```

### 10.2 数据库备份到 OSS

```bash
# ossutil 安装
wget https://gosspublic.alicdn.com/ossutil/1.7.19/ossutil64 -O /usr/local/bin/ossutil
chmod +x /usr/local/bin/ossutil
ossutil config -e oss-cn-hangzhou-internal.aliyuncs.com \
               -i $OSS_AK -k $OSS_SK
```

`/home/voxpress/backup.sh`：
```bash
#!/usr/bin/env bash
set -euo pipefail
TS=$(date +%Y%m%d-%H%M)
OUT=/tmp/voxpress-$TS.dump
pg_dump -h 127.0.0.1 -U voxpress -d voxpress -Fc -f "$OUT"
ossutil cp "$OUT" oss://voxpress-media-prod/db-backups/ -f
rm -f "$OUT"
```

crontab：
```cron
0 3 * * * /home/voxpress/backup.sh >> /var/voxpress/logs/backup.log 2>&1
```

### 10.3 本地媒体目录清理（兜底）

```cron
# 每天凌晨清理 3 天前的音频/视频缓存
30 2 * * * find /var/voxpress/audio -type f -mtime +3 -delete
35 2 * * * find /var/voxpress/video -type f -mtime +3 -delete
```

### 10.4 升级流程

**后端（ECS 上）**：

```bash
su - voxpress
cd ~/voxpress-api
git pull --ff-only
source .venv/bin/activate
pip install -e .
alembic upgrade head
exit

sudo systemctl restart voxpress-api voxpress-worker
journalctl -u voxpress-api -n 50 --no-pager
```

**前端（本地开发机 → ECS）**：

```bash
cd /path/to/voxpress
git pull --ff-only
npm ci              # 锁文件变了才需要，不变可跳过
npm run build
rsync -avz --delete ./dist/ voxpress@<ECS-IP>:/var/www/voxpress-web/
# Nginx 不用 reload，静态文件直接生效；index.html 设了 no-cache，客户端刷新即拿新版
```

若仅改了前端文案/样式，跳过后端步骤；若后端新增/改了 API，通常要**先后端再前端**（避免前端向老后端调不存在的接口）。

### 10.5 健康巡检 + 告警

`/home/voxpress/healthcheck.sh`：
```bash
#!/usr/bin/env bash
R=$(curl -sf http://127.0.0.1:8787/api/health) || { echo "API DOWN"; exit 1; }
echo "$R" | jq -e '.db_ok and .dashscope_enabled' >/dev/null || { echo "BAD: $R"; exit 1; }
echo OK
```

每 5 分钟一次 + 钉钉告警：
```cron
*/5 * * * * /home/voxpress/healthcheck.sh || curl -s -X POST "https://oapi.dingtalk.com/robot/send?access_token=..." -H 'Content-Type: application/json' -d '{"msgtype":"text","text":{"content":"voxpress 健康检查失败"}}'
```

### 10.6 故障诊断顺序（推荐 runbook）

服务异常时**从配置往外查**，不要先 `systemctl status`。一次完整链路：

**Step 1：核对配置（登 App 机第一动作）**

```bash
ssh-relay 47.237.81.215
cd /home/work/app/voxpress-api
grep -E "^VOXPRESS_(DB_URL|CORS_ORIGINS|HOST|PORT)" .env
```

确认：DB host 指向哪台、CORS 是否含当前域名/EIP。

**Step 2：后端 self-check**

```bash
curl -s http://127.0.0.1:8787/api/health | jq
```

- `db:false` 或超时 → 跳 Step 3
- 完全连不上 → `systemctl status voxpress-api`、`journalctl -u voxpress-api -n 100`

**Step 3：App → PG 连通性**

```bash
PG_HOST=$(grep ^VOXPRESS_DB_URL .env | sed -E 's|.*@([^:/]+).*|\1|')
timeout 5 bash -c "</dev/tcp/$PG_HOST/5432" && echo OPEN || echo BLOCKED

PGPASSWORD=$(grep ^VOXPRESS_DB_URL .env | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|') \
  psql -h "$PG_HOST" -U voxpress -d voxpress -c "select 1"
```

- `BLOCKED` → PG 机的 ufw 或阿里云安全组没放行 App 子网
- psql 报 `no pg_hba.conf entry` → PG 的 pg_hba 没放行 App 子网
- psql 报 `password authentication failed` → 密码或角色错
- timeout → PG 没起来或网络中断

**Step 4：PG 端核查（ssh-relay 到 PG 机）**

```bash
ssh-relay 43.98.194.178
systemctl is-active postgresql
sudo -u postgres psql -l | grep voxpress           # 库存在
sudo -u postgres psql -c "\du voxpress"            # 角色存在
grep voxpress /etc/postgresql/16/main/pg_hba.conf  # 客户端子网
ufw status verbose | grep 5432                     # 防火墙
tail -50 /var/log/postgresql/postgresql-16-main.log
```

**Step 5：Worker 自身**

```bash
systemctl status voxpress-worker
journalctl -u voxpress-worker -n 80 --no-pager
tail -200 /var/voxpress/logs/worker.log
```

Worker 启动时立即建 DB 连接池，**DB 不通就 1/FAILURE 重启循环**。所以排到 Step 5 看 worker 日志通常已经定位完。

**Step 6：Nginx（App 机 8080）**

```bash
nginx -t
ss -ltnp | grep 8080
curl -sS -H "Host: app.speechfolio.com" http://127.0.0.1:8080/api/health
tail -30 /var/log/nginx/error.log
```

**Step 7：SLB / 公网（阿里云控制台）**

- SLB 后端组健康检查状态
- 监听规则是否还指向当前 ECS 实例
- SSL 证书有效期

**Step 8：DNS 与客户端**

```bash
dig app.speechfolio.com +short
```

浏览器 DevTools → Network 看 CORS、HTTPS、状态码。

**经验**：~90% 的故障在 Step 1–4 定位。跳过 Step 1 直接 `systemctl` 是常见的浪费时间方式。

### 10.7 ECS 重建 / EIP 漂移回灌清单

阿里云 ECS 重启换可用区、重建实例、换 EIP 都会让 IP 变化。**不只 EIP 会变，私网 IP 也可能漂**——本次线上故障的根因就是 App 机私网 IP 从 `192.168.233.64` 漂到 `.81`，但 PG 端 ACL 写死单 IP `.64/32`，于是 worker 全挂。

#### A. 私网 IP 变了（重启/重建/换可用区都可能）

- [ ] **PG 机 `pg_hba.conf` 用子网而不是单 IP**：`host voxpress voxpress 192.168.233.0/24 scram-sha-256`，避免每次都改。改完 `systemctl reload postgresql`
- [ ] **PG 机 `ufw` 用子网**：`ufw allow from 192.168.233.0/24 to any port 5432 proto tcp`
- [ ] 阿里云**安全组**入方向规则也用子网（如果之前写死单 IP）
- [ ] App 机 `.env VOXPRESS_DB_URL`：通常不用改（指向的是 PG 的内网 IP，PG 没动）

#### B. 公网 EIP 变了

- [ ] App 机 nginx `server_name` 加新 EIP/域名，**清掉旧 EIP**
- [ ] App 机 `.env VOXPRESS_CORS_ORIGINS` 含新域名（前端构建里 `VITE_API_BASE` 也要更新，见 §8.3）
- [ ] **阿里云 SLB 后端服务器组**：移除旧实例、加入当前 ECS（或确认健康检查仍通过）
- [ ] 域名 DNS A 记录指向新 EIP（如果是直连模式）
- [ ] 阿里云安全组入方向规则更新
- [ ] 抖音 `cookie.txt`：换 IP 偶尔触发风控，跑 `/api/cookie/test` 验证
- [ ] 如果用 nginx 直签 Let's Encrypt（非线上现状）：DNS 切到新 IP 后 `certbot renew --force-renewal`

#### C. 实例 ID 变了（整体重建）

- [ ] SLB 后端组重新挂当前 ECS（旧实例 ID 已失效）
- [ ] 云监控/告警按 `instance_id` 配置的规则刷新
- [ ] crontab / systemd timer 重装：备份脚本（§10.2）、媒体清理（§10.3）、healthcheck（§10.5）、cookie 巡检
- [ ] 抖音 `cookie.txt`、DashScope key、OSS AK/SK 等密钥按 §6.2 重新配
- [ ] 检查 `~/.ssh/known_hosts`：本地的旧 host key 要删，团队成员同步

#### 治本建议（避免每次踩同样坑）

1. **PG 改用 PrivateZone 私网域名**（阿里云免费）：把 `192.168.233.52` 起个 `pg.voxpress.internal` 解析，App `.env` 改成 `postgresql+asyncpg://voxpress:***@pg.voxpress.internal/voxpress`。下次 PG 漂 IP 只改 PrivateZone 一处。
2. **App ECS 把 ENI 主私网 IP 设成"指定"** 而不是"自动分配"，从源头避免重启漂移。
3. **DB ACL 写子网而不是单 IP**（A 节），是上面两条的兜底。

---

## 11. 上线后的调参节奏

**Day 1**：保守参数（`download=2, organize=4`），跑 50 条观察：
- DashScope 日志有没有 429
- 抖音下载是否 403 / 风控
- `/var/voxpress/audio` 和 OSS 都在正常写

**Week 1**：并发恢复到默认（`download=4, correct=8, organize=8`），查看 `task_stage_runs` 表里每阶段平均耗时，留意 organize 是否有积压。

**Month 1**：如果日量稳定到 1500+，按此顺序放大：
1. DashScope 继续提额（通常比升机器更有效）
2. `organize_concurrency` 提到 12
3. 才考虑升 8C16G 或把 worker 拆到第二台机

---

## 12. 踩过的坑（部署时务必避开）

**基础设施/后端**：

1. **`/tmp` 是 tmpfs**：一定走 `/var/voxpress/*`，`.env` 里显式配 `VOXPRESS_AUDIO_DIR / VOXPRESS_VIDEO_DIR`
2. **OSS endpoint 别写错**：`internal` 的才免流量费；写成公网 endpoint 带宽费能翻几倍
3. **抖音 cookie 每 2–4 周需要手动换一次**，到期后所有 download 都会失败，建议定时跑 `/api/cookie/test` 巡检
4. **DashScope 默认 RPM 配额真不够**，不提额跑批量一定会 429，而且当前 runner 里没自动退避（REVIEW_v2 里的已知点），会直接失败。上线前务必申请提额
5. **Nginx 对 SSE 一定要关 `proxy_buffering`**，不然前端进度条永远不动
6. **`VOXPRESS_CORS_ORIGINS` 别忘改**，默认的 localhost 不改的话浏览器会跨域失败
7. **systemd 的 `EnvironmentFile` 不支持 shell 语法**，`.env` 里不要写 `$VAR` 引用，也不要加引号
8. **REVIEW_v2 里的 Blocker 建议在上线前至少修掉两条**：media proxy 的 `follow_redirects=True`（SSRF）和 SSE 队列满时静默丢事件（会让前端进度卡住）

**前端（dashboard）**：

9. **`VITE_*` 是构建时注入**，不是运行时读；改完 `.env.production` 必须重跑 `npm run build`，否则上传的还是旧配置
10. **`VITE_USE_MOCK=false` 生产必须关**，开着所有数据都是 mock；同理 `VITE_ENABLE_TWEAKS` 也建议关，避免暴露调试面板
11. **三处域名要对齐**：前端 `VITE_API_BASE` / 后端 `VOXPRESS_CORS_ORIGINS` / Nginx `server_name`，任一处不一致都会 CORS 或 404
12. **`index.html` 必须 `no-cache`**，否则发布了新版入口仍被 CDN 或浏览器缓存，用户看到的还是老页；`/assets/*` 反过来要长缓存 + `immutable`（Vite 已经在文件名里带哈希）
13. **rsync 用 `--delete`**：不用的话老版本的 js/css 会留在服务器上，磁盘慢慢涨；但注意**先确认目标目录正确**，别把 `/var/www/` 当成 `/var/www/voxpress-web/` 推错位置

**双机拓扑 / ECS 重建**：

14. **PG 拆机后 ufw + pg_hba 双层 ACL**：单机部署时 PG 走 unix socket 没这问题，拆机后客户端走 TCP，**两层都要放行**。只改 pg_hba 不改 ufw 会 timeout（TCP 层就被拦）；只改 ufw 不改 pg_hba 会 auth fail。建议都用子网（§10.7-A）。本次故障的根因。
15. **ECS 重建/重启不只换 EIP，私网 IP 也会漂**：本次 App 机私网从 `192.168.233.64` 漂到 `.81`，pg_hba 写死 `.64/32` 直接挂。固定 ENI 主私网 IP 或用子网放行（§10.7）。
16. **Nginx `server_name` 残留旧 EIP**：线上仍能看到 `43.98.200.159 43.98.204.138`，是历史 EIP 漂移没收尾，不影响功能但会迷惑后人核对部署。维护时顺手清掉。
17. **登机第一动作是 `cat .env` 不是 `systemctl status`**：从配置往外查（§10.6 标准顺序）。跳过 Step 1 直接 `systemctl` 经常导致按文档假设瞎排查（如假设 PG 在本机，而实际是拆机）。
18. **`.env` 是脚本生成的**：文件头有 `# Auto-generated YYYY-MM-DDTHH:MM:SS+08:00` 注释。换密码、迁机时如何重新生成（生成器位置/约定）目前文档缺失，team 需要补一份。

---

## 13. 账单预估

**按 400 条/天 × 30 天（你当前的用量）估算**：

| 项 | 依据 | 月费 |
|---|---|---|
| ECS g7 4C8G 年付 | ¥2040/年 摊薄 | ¥170 |
| ESSD 80GB | | ¥24 |
| EIP 保有 | 按量模式 | ¥0 |
| 公网出流量 | API 响应 + 媒体代理 ≈ 20GB | ¥15 |
| OSS 标准存储 | 400 × 30 × 5MB ≈ 60GB 累积 | ¥8 |
| OSS 请求费 | put/get 约几十万次 | ¥5 |
| **硬件合计** | | **~¥222/月** |
| DashScope qwen3.6-plus（organize） | 单篇 input 2k + output 3k ≈ ¥0.040 | |
| DashScope qwen-turbo（correct） | 单篇 ≈ ¥0.002 | |
| DashScope ASR | 5 分钟音频 ≈ ¥0.066 | |
| DashScope annotate_background | 单篇 ≈ ¥0.011 | |
| **DashScope 单篇总成本** | | **≈ ¥0.12** |
| DashScope 月总计 | 400 × 30 × ¥0.12 | **~¥1440/月** |
| **总合计** | | **~¥1660/月** |

**用量—费用关系**：100 条/天 → 总 ~¥580/月；400 条/天 → ~¥1660/月；1000 条/天 → ~¥3820/月。硬件固定，浮动的几乎全是 DashScope。

**想压 DashScope 成本的两个杠杆**：
- **把 organize 主力模型从 `qwen3.6-plus` 切成 `qwen-plus`**（input ¥0.0008、output ¥0.002/千 tokens）：单篇 organize 从 ¥0.040 降到 ¥0.007，总成本省 ~50%。代价是长视频的保留度下降，这是 REVIEW_v2 里讨论过的质量/成本权衡
- **批量场景关掉 annotate_background**（通过 settings PATCH 把 `llm.background_notes_enabled=false`）：每篇省 ¥0.011，幅度不大但属于"不损失主体观感"的纯省

**什么时候升 RDS / 拆 Worker**：
- 硬件成本占比 < 20%，升硬件带来的节省很有限
- 真需要扩容时先加一台 ECS 单独跑 Worker（¥200/月），数据库共用，能近似把吞吐翻倍
- 单日稳定超过 2000 条且 organize 持续积压时才考虑 RDS 高可用版

---

## 附：一次性部署脚本骨架

`bootstrap.sh`（到了 ECS 上 sudo 执行一遍）：
```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. 包
apt update && apt upgrade -y
apt install -y build-essential git curl wget jq unzip ufw ffmpeg \
               python3.12 python3.12-venv python3-pip \
               nginx certbot python3-certbot-nginx \
               postgresql-16 postgresql-contrib-16 tzdata

# 2. 时区 & 防火墙
timedatectl set-timezone Asia/Shanghai
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp
ufw --force enable

# 3. 用户 & 目录
useradd -m -s /bin/bash voxpress || true
mkdir -p /var/voxpress/{audio,video,logs}
chown -R voxpress:voxpress /var/voxpress

# 4. Postgres
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='voxpress') THEN
    CREATE ROLE voxpress WITH LOGIN PASSWORD '$PG_PASSWORD';
  END IF;
END \$\$;
SELECT 'CREATE DATABASE voxpress OWNER voxpress' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='voxpress')\gexec
SQL
sudo -u postgres psql -d voxpress -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

echo "bootstrap done; next: clone repo as voxpress user, create .env, alembic upgrade head, install systemd units"
```

其余的（git clone / .env / systemd / nginx）保持手动按第 6–8 节跑，避免把密钥写死在脚本里。
