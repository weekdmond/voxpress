# Speechfolio / VoxPress 运维手册

生产环境的实况、配置与日常运维。配合 `DEPLOYMENT.md`(最初的部署方案)使用:前者是"打算怎么部",本手册是"实际部成了什么、日常怎么改"。

---

## 1. 架构总览

```
 用户浏览器
     │ HTTPS
     ▼
 Cloudflare Edge (speechfolio.com / www / app)
   - SSL termination (Let's Encrypt via CF Universal SSL)
   - Proxy (橙云) + DDoS + WAF
     │ HTTP
     ▼
 阿里云 SLB  43.98.204.138:80
     │ VPC 内网
     ▼
 App ECS  43.98.200.159 (公网)  /  192.168.233.64 (私网 eth0)
          Ubuntu 24.04.4 LTS · 4C8G · ESSD 99GB · ap-southeast-1a
          (前一台 47.236.244.180 / 192.168.233.51 已于 2026-04-27 释放)
   │
   ├─ nginx :8080
   │     ├─ /api/*            → 127.0.0.1:8787
   │     ├─ /api/tasks/stream → 127.0.0.1:8787  (SSE, proxy_buffering off)
   │     └─ /*                → /var/www/voxpress-web/
   ├─ uvicorn :8787   (FastAPI)
   └─ voxpress-worker (python 进程, systemd)
           │
           │ VPC 内网 ≈0.4ms
           ▼
 DB  ECS  43.98.194.178 (公网)  /  192.168.233.52 (私网 eth0)
          Ubuntu 24.04.4 LTS · 4C8G · ESSD 99GB · ap-southeast-1a (同 vSwitch)
   │
   └─ postgresql :5432   (listen 192.168.233.52, 127.0.0.1)

 旁挂(远端):
   - OSS bucket  fitagent @ ap-southeast-1  (公网 endpoint, 跨 region 给 DashScope 用)
   - DashScope   dashscope.aliyuncs.com     (北京/杭州)
   - 抖音        douyin.com                 (公网)
```

**关键端口**

App ECS(`43.98.200.159` / 私网 `192.168.233.64`):
| 端口 | 监听 | 组件 | 对外可达 |
|---|---|---|---|
| 22 | 0.0.0.0 | sshd | 公网(key-only) |
| 8080 | 0.0.0.0 | nginx | VPC(供 SLB) |
| 8787 | 127.0.0.1 | uvicorn | 仅本机 |

DB ECS(`43.98.194.178` / 私网 `192.168.233.52`):
| 端口 | 监听 | 组件 | 对外可达 |
|---|---|---|---|
| 22 | 0.0.0.0 | sshd | 公网(key-only) |
| 5432 | `192.168.233.52` + `127.0.0.1` | postgres | VPC,UFW 限 `192.168.233.64/32` |

UFW(App ECS):allow 22 / 80 / 443 / 8080(80/443 无 listener)。
UFW(DB ECS):allow 22;5432 限 `192.168.233.64/32`。

---

## 2. 域名 / Cloudflare

**Zone**

| Zone | speechfolio.com |
|---|---|
| Zone ID | `2bfde99e7f9eeb3917a34e64a87ea8e2` |
| 注册商 | Cloudflare Registrar |
| Nameservers | `autumn.ns.cloudflare.com`, `burt.ns.cloudflare.com` |

**DNS**(全部 Proxied,橙云)

| 记录 | 类型 | 值 |
|---|---|---|
| `@` | A | 43.98.204.138 |
| `www` | A | 43.98.204.138 |
| `app` | A | 43.98.204.138 |

**SSL / 重定向**

| 设置 | 值 | 说明 |
|---|---|---|
| SSL mode | **Flexible** | CF↔浏览器 HTTPS,CF↔源站 HTTP |
| Always Use HTTPS | on | 81 → 301 → 443 |
| Automatic HTTPS Rewrites | on | 混合内容自动 upgrade |

**子域规划**(当前 + 目标)

| 子域 | 当前 | 目标(阶段 2) |
|---|---|---|
| `speechfolio.com` / `www` | → SLB(dashboard) | → CF Pages(landing page) |
| `app.speechfolio.com` | → SLB(dashboard) | 保持 |
| `api.speechfolio.com` | 未用 | 未定(同域 /api 就够) |
| `docs.speechfolio.com` | 未用 | 文档站(阶段 3) |

---

## 3. 访问与账户

**SSH**

```bash
# App ECS  (43.98.200.159 / 私网 192.168.233.64)
ssh-relay 43.98.200.159                                                # alias, root
ssh -i ~/.ssh/tflyer-sg-inter-ssh-key-423.pem root@43.98.200.159
ssh -i ~/.ssh/tflyer-sg-inter-ssh-key-423.pem work@43.98.200.159

# DB ECS  (43.98.194.178 / 私网 192.168.233.52)
ssh-relay 43.98.194.178
ssh -i ~/.ssh/tflyer-sg-inter-ssh-key-423.pem root@43.98.194.178
ssh -i ~/.ssh/tflyer-sg-inter-ssh-key-423.pem work@43.98.194.178
```

**work 用户**(两台机都有,配置一致)

| 项 | 值 |
|---|---|
| uid/gid | 1000 / 1000 |
| 登录密码 | 无(`passwd -d work`,只能 SSH key 登录) |
| sudo | `NOPASSWD` via `/etc/sudoers.d/90-work` |
| authorized_keys | 复用 root 的 |

---

## 4. 关键路径

**App ECS(`43.98.200.159`)**

| 用途 | 路径 |
|---|---|
| 后端源码 | `/home/work/app/voxpress-api/` |
| 虚拟环境 | `/home/work/app/voxpress-api/.venv/` |
| 后端 `.env`(mode 600) | `/home/work/app/voxpress-api/.env` |
| 前端 dist | `/var/www/voxpress-web/` |
| 服务日志 | `/var/voxpress/logs/{api,worker}.log` |
| 媒体缓存(非 `/tmp`) | `/var/voxpress/{audio,video}/` |
| systemd units | `/etc/systemd/system/voxpress-{api,worker}.service` |
| nginx 配置 | `/etc/nginx/sites-available/voxpress` |

**DB ECS(`43.98.194.178`)**

| 用途 | 路径 |
|---|---|
| PG 数据目录 | `/var/lib/postgresql/16/main/` |
| PG 主配置 | `/etc/postgresql/16/main/postgresql.conf` |
| 访问控制 | `/etc/postgresql/16/main/pg_hba.conf` |
| PG 密码备份 | `/root/pg_voxpress.pass`、`/home/work/.pg_pass` |

> App ECS 上(镜像自带的)`postgres` 已 `stop + disable`,DB 全量在 DB ECS;App ECS 不再跑 PG。

---

## 5. 环境变量(`.env` 结构,脱敏)

```dotenv
# database (跨机: app ECS -> DB ECS 私网)
VOXPRESS_DB_URL=postgresql+asyncpg://voxpress:<密码>@192.168.233.52/voxpress
VOXPRESS_HOST=127.0.0.1
VOXPRESS_PORT=8787
VOXPRESS_CORS_ORIGINS=https://app.speechfolio.com,https://speechfolio.com,https://www.speechfolio.com,http://43.98.200.159,http://43.98.204.138

# local media (NOT /tmp)
VOXPRESS_AUDIO_DIR=/var/voxpress/audio
VOXPRESS_VIDEO_DIR=/var/voxpress/video

# pipeline
VOXPRESS_PIPELINE=real

# DashScope
VOXPRESS_DASHSCOPE_API_KEY=sk-...
VOXPRESS_DASHSCOPE_COMPATIBLE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VOXPRESS_DASHSCOPE_DEFAULT_LLM_MODEL=qwen3.6-plus
VOXPRESS_DASHSCOPE_DEFAULT_CORRECTOR_MODEL=qwen-turbo-latest
VOXPRESS_DASHSCOPE_DEFAULT_ASR_MODEL=qwen3-asr-flash-filetrans

# concurrency (Day 1 conservative)
VOXPRESS_MAX_PIPELINE_CONCURRENCY=8
VOXPRESS_DOWNLOAD_CONCURRENCY=2
VOXPRESS_TRANSCRIBE_CONCURRENCY=4
VOXPRESS_CORRECT_CONCURRENCY=6
VOXPRESS_ORGANIZE_CONCURRENCY=4
VOXPRESS_SAVE_CONCURRENCY=4

# OSS (region 必须和 ECS 同一个, 否则走 internal endpoint 不通;
# 目前是 ap-southeast-1 公网 endpoint, 因 bucket 也在 SG 但 DashScope 在北京要拉 URL)
VOXPRESS_OSS_REGION=ap-southeast-1
VOXPRESS_OSS_ENDPOINT=oss-ap-southeast-1.aliyuncs.com
VOXPRESS_OSS_BUCKET=fitagent
VOXPRESS_OSS_ACCESS_KEY_ID=LTAI...
VOXPRESS_OSS_ACCESS_KEY_SECRET=...
VOXPRESS_OSS_SIGN_EXPIRES_SEC=3600
```

抖音 `cookie.txt` 不走 `.env`,通过 Dashboard 设置页或 `POST /api/settings/cookie` 上传,落 DB `settings` 表。

---

## 6. Postgres(独立 DB ECS)

**主机**:`43.98.194.178` / 私网 `192.168.233.52`(跟 App ECS 同 VPC 同 vSwitch `vsw-t4n1nuuixbyox5bf0e6vh`)。

**DB**

| 项 | 值 |
|---|---|
| Database | `voxpress` |
| Owner / App user | `voxpress` |
| 监听 | `192.168.233.52:5432` + `127.0.0.1:5432` + unix socket |
| 超级用户 | `postgres`(peer auth,本机) |
| 扩展 | `pg_trgm 1.6`, `pgcrypto 1.3`, `vector 0.6`(apt), `plpgsql` |

**访问控制**

`/etc/postgresql/16/main/pg_hba.conf` 额外加了一行允许 App ECS 私网:

```
host    voxpress    voxpress    192.168.233.64/32    scram-sha-256
```

UFW:`allow from 192.168.233.64 to any port 5432 proto tcp`。
阿里云安全组:入方向放行 5432 给 App ECS 私网(同 VPC 内网都放行也可)。

> 换 App ECS 时记得**两边都改**:DB ECS 的 `pg_hba.conf` 和 UFW 都要把旧 IP 删掉、新 IP 加上,然后 `systemctl reload postgresql`。

**4C8G 调优**(已写入 `/etc/postgresql/16/main/postgresql.conf`)

```conf
listen_addresses = '192.168.233.52,127.0.0.1'
max_connections = 200
shared_buffers = 2GB
effective_cache_size = 6GB
work_mem = 16MB
maintenance_work_mem = 512MB
wal_buffers = 16MB
checkpoint_completion_target = 0.9
random_page_cost = 1.1
log_min_duration_statement = 500ms
```

**pgvector 版本**:Ubuntu apt 仓库只到 0.6。若要 0.7+(halfvec、iterative scan)需加 PGDG 源升级。

**备份**:建议在 **DB ECS 本机**跑 `pg_dump` 到 OSS,避免把数据绕道 App ECS。相关脚本待启用(见 §9.4)。

---

## 7. systemd 服务

两个 unit 都 `WorkingDirectory=/home/work/app/voxpress-api`,`User=work`,`EnvironmentFile=.env`,`Restart=always`。

> **拆 DB 后已去掉 `After=postgresql.service` / `Requires=postgresql.service`** —— PG 现在在远端,app ECS 本机的 `postgresql.service` 已停用,若保留依赖会导致 api/worker 跟着"被拖停"。

```bash
# 状态 / 启动 / 停止 / 重启
systemctl status voxpress-api voxpress-worker
systemctl restart voxpress-api              # 改了 .env / 源码后
systemctl restart voxpress-worker

# 跟随日志
journalctl -u voxpress-api -f
tail -f /var/voxpress/logs/api.log          # systemd 同时落盘
```

**重启窗口约 3 秒**:uvicorn 冷启动期间 SLB health check 会短暂拿到 502,属预期。

---

## 8. Nginx

- `/etc/nginx/sites-available/voxpress`(唯一 enabled site,default 已删)
- `listen 8080`,`server_name app.speechfolio.com speechfolio.com www.speechfolio.com 47.236.244.180 _;`
- 关键点:
  - `location /api/tasks/stream`:`proxy_buffering off`、`proxy_read_timeout 24h`、`chunked_transfer_encoding on`(SSE 必需)
  - `/assets/*`:`Cache-Control: public, max-age=31536000, immutable`
  - `/index.html`:`Cache-Control: no-cache, no-store, must-revalidate`
  - 其它 URL:`try_files $uri $uri/ /index.html;`(SPA fallback)

---

## 9. 标准运维流程

### 9.0 重建 App ECS(机器丢/释放后的紧急流程)

如果当前 App ECS 死了(实例释放、网络异常、磁盘损坏),从一台干净 Ubuntu 24.04 机器到恢复线上,大致流程:

1. 阿里云开新 ECS(同 region `ap-southeast-1a`,4C8G,Ubuntu 24.04),拿到公网 + 私网 IP
2. (**如果是镜像克隆**)启动后:停 `voxpress-api/worker`,`systemctl disable --now postgresql@16-main`,清 `/home/work/app` / `/var/voxpress` / `/var/www`,卸 `nginx-old config`(若不需要再清)
3. 装包:`apt install -y nginx postgresql-client-16 build-essential python3.12-venv ffmpeg ufw`(若是镜像克隆这些都已经在)
4. 创建 `work` 用户(同 §3),目录 `/home/work/app`、`/var/voxpress/{audio,video,logs}`、`/var/www/voxpress-web`
5. 从本地 `rsync` 后端代码到 `/home/work/app/voxpress-api`(参照 §9.1)
6. 写 `.env`(参照 §5,DB URL 指 DB ECS 私网,CORS 含 speechfolio 域名),mode 600
7. 写 systemd units(`voxpress-api`、`voxpress-worker`)—— **不要带 `After=postgresql.service`**
8. 写 nginx site:server_name 含 speechfolio 域名 + 新 IP;listen 8080
9. **DB ECS 上**加 pg_hba 行 + UFW 规则放新 App ECS 私网 IP,删旧 IP(参照 §6)
10. 本地 build 前端 + rsync `dist/` 到 `/var/www/voxpress-web/`
11. `systemctl start voxpress-api voxpress-worker`,`systemctl reload nginx`
12. **更新 SLB 后端 RS** 到新 App ECS 私网 IP:8080(用户在阿里云控制台改)
13. CF 不需要改(只要 SLB 公网 IP 不变)
14. 验证 `https://app.speechfolio.com/api/health` → 200

### 9.1 后端代码更新(rsync,推荐)

仓库是 monorepo(`github.com/weekdmond/voxpress`),服务器上 clone 过一次。日常更新**不走 `git pull`**,直接 rsync 本地 workspace(能推未 push 的 commit):

```bash
# 本地
rsync -az --delete \
  --exclude='.git/' --exclude='.venv/' --exclude='node_modules/' \
  --exclude='__pycache__' --exclude='.pytest_cache/' --exclude='.ruff_cache/' \
  --exclude='.env' --exclude='.env.local' \
  --exclude='voxpress.db' --exclude='logs/' --exclude='.DS_Store' \
  -e "ssh -i ~/.ssh/tflyer-sg-inter-ssh-key-423.pem" \
  /Users/auston/cowork/dy_docs/voxpress-api/ \
  work@43.98.200.159:/home/work/app/voxpress-api/

# 服务器
ssh ...180 '
  cd /home/work/app/voxpress-api
  sudo -u work .venv/bin/pip install -q -e .   # pyproject 有新依赖时
  sudo -u work .venv/bin/alembic upgrade head  # 有新 migration 时
  systemctl restart voxpress-api voxpress-worker
'
```

### 9.2 前端发布

```bash
# 本地
cd /Users/auston/cowork/dy_docs/voxpress

cat > .env.production <<EOF
VITE_API_BASE=https://app.speechfolio.com
VITE_SSE_BASE=https://app.speechfolio.com
VITE_USE_MOCK=false
VITE_ENABLE_TWEAKS=false
EOF

npm run build

rsync -az --delete -e "ssh -i ~/.ssh/tflyer-sg-inter-ssh-key-423.pem" \
  ./dist/ work@43.98.200.159:/var/www/voxpress-web/

rm .env.production   # 生产配置不入库,build 完即删
```

Nginx 不用 reload:`index.html` 是 no-cache,浏览器刷新即拿新版;`/assets/*` 文件名带 hash,旧的由 `--delete` 清理。

### 9.3 数据库迁移(本地 → 线上,覆盖)

目标是 **DB ECS** (`43.98.194.178`),不是 App ECS。最快做法是**从本地直接 stream**,用本地作为 SSH pipe(App ECS 可停也可不停,取决于你是否从 App ECS 本机的 PG dump —— 当前 DB 已迁走,本地 → DB ECS 就够):

```bash
# (可选) 若不想导致写入中断, 先停 app
ssh -i ~/.ssh/tflyer-sg-inter-ssh-key-423.pem root@43.98.200.159 \
  'systemctl stop voxpress-api voxpress-worker'

# DB ECS: 重建空库 + 扩展
ssh -i ~/.ssh/tflyer-sg-inter-ssh-key-423.pem root@43.98.194.178 "sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='voxpress' AND pid<>pg_backend_pid();
DROP DATABASE IF EXISTS voxpress;
CREATE DATABASE voxpress OWNER voxpress ENCODING 'UTF8';
\c voxpress
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
GRANT ALL PRIVILEGES ON DATABASE voxpress TO voxpress;
SQL"

# stream: 本地 pg_dump -> DB ECS pg_restore
pg_dump -Fc -U auston -h localhost -d voxpress --no-owner --no-privileges \
  | ssh -i ~/.ssh/tflyer-sg-inter-ssh-key-423.pem root@43.98.194.178 \
    'PG_PASS=$(cat /root/pg_voxpress.pass); PGPASSWORD=$PG_PASS \
     pg_restore --no-owner --no-privileges -U voxpress -h 127.0.0.1 -d voxpress'

# 启 app
ssh -i ~/.ssh/tflyer-sg-inter-ssh-key-423.pem root@43.98.200.159 \
  'systemctl start voxpress-api voxpress-worker'
```

> **若 dump 源是 App ECS 本机的 PG**(例如从备份恢复):把 `pg_dump` 命令改成 `ssh ...180 'pg_dump -h 127.0.0.1 ...'`,两头 SSH 都走本地作 pipe hub。`COMMENT ON EXTENSION` 的 "must be owner" 警告无害。

### 9.4 DB 备份到 OSS(暂未启用)

**在 DB ECS 本机**跑,不要从 App ECS 通过网络拉数据:

```bash
# /home/work/backup.sh
#!/usr/bin/env bash
set -euo pipefail
TS=$(date +%Y%m%d-%H%M)
OUT=/tmp/voxpress-$TS.dump
PG_PASS=$(cat /home/work/.pg_pass)
PGPASSWORD=$PG_PASS pg_dump -Fc --no-owner --no-privileges \
  -U voxpress -h 127.0.0.1 -d voxpress -f "$OUT"
ossutil cp "$OUT" oss://fitagent/db-backups/ -f
rm -f "$OUT"
```

cron:`0 3 * * * /home/work/backup.sh >> /var/log/voxpress-backup.log 2>&1`。

### 9.5 Cloudflare DNS 改动(API)

```bash
export CF_TOKEN="cfut_..."     # Custom token: Zone.DNS Edit + Zone Settings Edit + Zone Read
API=https://api.cloudflare.com/client/v4
ZONE_ID=2bfde99e7f9eeb3917a34e64a87ea8e2

# 查记录
curl -s -H "Authorization: Bearer $CF_TOKEN" "$API/zones/$ZONE_ID/dns_records" | jq

# 加记录(proxied)
curl -s -X POST -H "Authorization: Bearer $CF_TOKEN" -H "Content-Type: application/json" \
  "$API/zones/$ZONE_ID/dns_records" \
  -d '{"type":"A","name":"xxx.speechfolio.com","content":"43.98.204.138","ttl":1,"proxied":true}'

# 改 SSL mode
curl -s -X PATCH -H "Authorization: Bearer $CF_TOKEN" -H "Content-Type: application/json" \
  "$API/zones/$ZONE_ID/settings/ssl" -d '{"value":"full"}'
```

---

## 10. 已知风险 / 待办

### 10.1 必须尽早做

- [ ] **OSS AK/SK 轮换**:当前 AK/SK 在部署期间通过聊天明文传递过。去 RAM 控制台禁用现 AK、新建 AK、替换 `.env` 里 `VOXPRESS_OSS_ACCESS_KEY_ID/SECRET`,重启 api。
- [ ] **DB 备份启用**:`/home/work/backup.sh` (DB ECS) + cron + OSS,参照 §9.4。**目前没有自动备份,DB 挂了数据就没了**。
- [ ] **SSL 升级到 Full (strict)**:当前 Flexible 下 CF→源站是 HTTP。做法:
  1. CF → SSL/TLS → Origin Server → Create Origin Certificate(15 年免费证书,限 CF 信任链)
  2. 证书 + key 拷到服务器 `/etc/ssl/cloudflare/`
  3. nginx 加 `listen 443 ssl`,挂证书
  4. SLB 也要配 443 监听,或让 CF 直接回源到 8080 改走 https + 自定义端口
  5. CF SSL mode 从 Flexible 切到 **Full (strict)**
- [ ] **抖音 cookie 过期监控**:当前 cookie 在 DB `settings` 表里;每 2–4 周手动换一次。可以起一个 cron 调 `/api/cookie/test`,失败发告警。
- [ ] **清理 App ECS 上的旧 PG 数据目录**:镜像带的 PG 已 `stop + disable`,但 `/var/lib/postgresql/` 仍占 ~120MB。确认稳定后可 `apt purge postgresql-16 postgresql-contrib-16 && rm -rf /var/lib/postgresql`。
- [ ] **App ECS 是 stateful**:文件系统里有 `.env`(秘钥)和前端 dist。机器一释放就全没,重建必须按本手册流程重做(rsync 代码 + 写 .env + 配 nginx server_name + 配 CORS + DB ECS 加 pg_hba/UFW 新 IP)。考虑用阿里云**实例镜像**做定期快照。前一台 `47.236.244.180` 就是这样直接释放,2026-04-27 走过完整重建流程。

### 10.2 持续提醒

- **DashScope RPM 提额**:`qwen3.6-plus` 默认 RPM 跑不动批量,提工单提到 300+,`qwen3-asr-flash-filetrans` 提并发任务到 20+。
- **/var/voxpress 清理 cron**:`DEPLOYMENT.md §10.3` 有脚本,尚未启用。建议 3 天外临时文件自动清。
- **健康巡检**:`DEPLOYMENT.md §10.5` 提到的钉钉告警 cron,尚未启用。
- **CF API token `cfut_G0Kp...`**:部署期用过,建议登录 CF revoke。
- **部署 dump 残留**:本地 `/tmp/voxpress-*.dump`、服务器 `/tmp/voxpress.dump`(含完整 DB)保留状态;定期清。

### 10.3 阶段推进

**阶段 2 —— Landing page**

- 新建静态站仓库(Next.js 或 Astro)
- 部署到 CF Pages(zone 已在同账号,Add Custom Domain 即自动挂 DNS)
- 把 `@` + `www` 的 A 记录改成 CNAME 指 Pages(或通过 Pages 后台自动改)
- `app.*` 保持

**阶段 3 —— 订阅支付**

- **支付**:Stripe Checkout + Billing Portal(最快)或 Paddle(MOR,省 VAT 合规)
- **Auth**:Clerk(付费,magic link + 社交登录)或 Supabase Auth(免费自托管)
- **订阅表**:`users`、`subscriptions`、`usage_ledger` 加到现 Postgres
- **限流**:voxpress pipeline 里按 plan 封顶 ASR 分钟数 / organize 次数
- **Stripe webhook**:`/api/webhooks/stripe` 处理 `customer.subscription.*` 事件

---

## 11. 当前数据快照(2026-04-27,App ECS 重建后)

```
位置        : DB ECS 43.98.194.178 (192.168.233.52:5432)
tasks       = 1354+ (随 worker 持续增长)
videos      = 2563+
articles    = 1104+
transcripts = 1104+
alembic     = e2a9b7c4d1f0  (allow auto task trigger)
```

**版本时间线**

| 时间 | 事件 |
|---|---|
| 2026-04-23 | 首次部署到 `47.236.244.180`(App + DB 同机) |
| 2026-04-24 | DB 拆出独立 ECS `43.98.194.178`,App ECS 上 PG `disable` |
| 2026-04-24 | speechfolio.com 接入(CF + SLB),Schema 升至 `c8a4d2e7f9b1` |
| 2026-04-26 | Schema 升至 `e2a9b7c4d1f0`(auto task trigger) |
| 2026-04-27 | 旧 App ECS `47.236.244.180` 释放,新 App ECS `43.98.200.159` 顶上,DB 不变 |

---

## 12. 一些约定(避免踩坑)

1. **`.env` 永远不进 git**(已在 `.gitignore`);服务器 `.env` mode 600。
2. **不要在 `.env` 里用 shell `$VAR` 引用** —— systemd `EnvironmentFile` 不展开变量,也不解引号。
3. **媒体目录永远不放 `/tmp`**(tmpfs,重启即失)—— 使用 `VOXPRESS_AUDIO_DIR/VIDEO_DIR` 指到 `/var/voxpress/*`。
4. **Nginx SSE location 必须关 buffering**,否则前端进度条永远不动。
5. **OSS endpoint 和 ECS 同 region** —— 跨 region 走 `internal` endpoint 直接失败;走公网则有流量费,且 DashScope 从北京拉 URL 必须用公网 endpoint(签名 URL 会基于此)。
6. **SLB 后端配置**:RS `192.168.233.64:8080`(App ECS eth0),健康检查 `GET /api/health`,SSE idle timeout ≥ 900s。**换 App ECS 时 SLB 后端 RS 必须跟着改**,否则全站 503。
9. **PG 在独立 DB ECS** (`192.168.233.52`),不再和 app 同机。App ECS 上的 `postgresql` 已 `stop + disable`;systemd unit 不要再加 `After=postgresql.service`。
7. **前端三处必须同步**:`VITE_API_BASE` / 后端 `VOXPRESS_CORS_ORIGINS` / Nginx `server_name`,任一不一致都会 CORS 失败或 404。
8. **`VITE_*` 是构建时注入**,改 `.env.production` 必须重跑 `npm run build`。

---

## 附:SLB 配置参考

- **后端 RS**:`192.168.233.64:8080`(App ECS eth0 内网,当前是 `43.98.200.159`)
- **协议**:HTTP
- **健康检查**:`GET /api/health`,期望 200
- **会话保持**:关闭(后端无状态,DB 在独立机,连接池各自维持)
- **Idle timeout**:≥ 900 秒(为 SSE 长连)
- **访问日志**:建议开,便于排查
