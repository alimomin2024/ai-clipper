# Deploy AI Clipper on Oracle Cloud (Always Free)

This guide targets a single **VM.Standard.A1.Flex** instance (**2 OCPU, 12 GB RAM**) in your tenancy **home region**. Do not use **VM.Standard.E2.1.Micro** (1 GB RAM); it cannot run Faster-Whisper and FFmpeg together.

## 1. Create the instance (OCI console)

1. Sign up for [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/) and complete verification.
2. **Compute → Instances → Create instance**
   - **Name:** `ai-clipper`
   - **Image:** Ubuntu 22.04 or 24.04 (aarch64)
   - **Shape:** `VM.Standard.A1.Flex`
   - **OCPU:** 2, **Memory:** 12 GB
   - **Boot volume:** 80–100 GB (stays within the 200 GB Always Free pool; leave room for encodes)
   - **Networking:** assign a **public IPv4**
   - **SSH keys:** add your public key
3. If creation fails with **Out of host capacity**, try another **availability domain** or home region (Chuncheon is not eligible for Always Free A1).

## 2. Network security (VCN)

**Networking → Virtual cloud networks → your VCN → Security lists → Ingress rules**

| Source        | Protocol | Port | Purpose        |
|---------------|----------|------|----------------|
| `0.0.0.0/0`   | TCP      | 22   | SSH            |
| `0.0.0.0/0`   | TCP      | 80   | HTTP (Certbot) |
| `0.0.0.0/0`   | TCP      | 443  | HTTPS          |

Do **not** expose port 8080 publicly; the app sits behind nginx on the VM.

Also configure **iptables** on Ubuntu if `ufw` is enabled:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## 3. Server bootstrap (SSH)

```bash
ssh ubuntu@YOUR_PUBLIC_IP

sudo apt-get update
sudo apt-get install -y git curl ca-certificates

# Docker (official convenience script)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
# Log out and back in so docker group applies
```

Optional: install **nginx** and **certbot** on the host (recommended) instead of inside the container:

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

## 4. Clone and configure the app

```bash
sudo mkdir -p /opt/ai-clipper
sudo chown "$USER:$USER" /opt/ai-clipper
git clone https://github.com/alimomin2024/ai-clipper.git /opt/ai-clipper
cd /opt/ai-clipper
```

Create `.env` at the repo root (used by Docker Compose):

```bash
cp .env.example .env
```

Edit `.env` for Always Free:

```env
HOST_BIND=127.0.0.1
PORT=8080

ENVIRONMENT=production
REQUIRE_ADMIN_KEY=true
ADMIN_API_KEY=CHANGE_ME_LONG_RANDOM_SECRET

MAX_CONCURRENT_WORKERS=1
CLEANUP_HOURS=24
MAX_UPLOAD_SIZE_MB=250
MAX_VIDEO_DURATION_SECONDS=900
MAX_TARGET_CLIPS=4

WHISPER_MODEL_DIR=/app/backend/storage/models/faster-whisper-base
```

Generate a strong admin key:

```bash
openssl rand -hex 32
```

## 5. Build and run with Docker

```bash
cd /opt/ai-clipper
docker compose build
docker compose up -d
```

Download the Whisper model **once** (needs internet on first run):

```bash
docker compose exec ai-clipper python /app/backend/scripts/prepare_offline.py
```

Health check (on the VM):

```bash
curl -sS http://127.0.0.1:8080/api/health | jq .
```

Expect `"status": "healthy"` and `"offline_whisper_model": true`.

Persist storage: `docker-compose.yml` already mounts `./backend/storage`. Back up this directory before rebuilding images.

## 6. Nginx reverse proxy

Create `/etc/nginx/sites-available/ai-clipper` (replace `clip.example.com`):

```nginx
# Upload limit must be >= MAX_UPLOAD_SIZE_MB in .env
client_max_body_size 300m;

map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80;
    server_name clip.example.com;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name clip.example.com;

    # certbot --nginx -d clip.example.com will fill these paths
    ssl_certificate     /etc/letsencrypt/live/clip.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/clip.example.com/privkey.pem;

    client_max_body_size 300m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Server-Sent Events for job progress (can run many minutes)
    location ~ ^/api/jobs/[^/]+/stream$ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 7200s;
        proxy_send_timeout 7200s;
    }
}
```

Enable the site:

```bash
sudo ln -sf /etc/nginx/sites-available/ai-clipper /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

TLS (after DNS A record points to the instance public IP):

```bash
sudo certbot --nginx -d clip.example.com
```

## 7. DNS

At your registrar (or RazorHost DNS):

- **A record:** `clip` → Oracle instance **public IPv4**
- Optional: `www` → same IP or CNAME to `clip.example.com`

## 8. Operations

**View logs**

```bash
cd /opt/ai-clipper && docker compose logs -f --tail=200
```

**Restart after code pull**

```bash
git pull
docker compose build
docker compose up -d
```

**Disk usage** (200 GB free tier fills quickly with video):

```bash
df -h
du -sh /opt/ai-clipper/backend/storage/*
```

Tune `CLEANUP_HOURS` and upload limits if disk is tight.

**Admin API** (when `REQUIRE_ADMIN_KEY=true`): send header `X-Admin-Key: YOUR_ADMIN_API_KEY` on `/api/admin/*` routes.

## 9. Optional: keep instance from appearing idle

Oracle may reclaim **idle** Always Free compute depending on policy and utilization. Lightweight options:

- External uptime monitor hitting `GET https://clip.example.com/api/health` every 5–15 minutes
- Or a **systemd timer** on the VM: `curl -fsS http://127.0.0.1:8080/api/health`

Avoid hammering the server with heavy synthetic encodes.

## 10. Free-tier product limits (recommended)

| Setting | Suggested value | Why |
|---------|-----------------|-----|
| `MAX_CONCURRENT_WORKERS` | 1 | Prevents OOM on 12 GB |
| `MAX_UPLOAD_SIZE_MB` | 250 | Disk + encode time |
| `MAX_VIDEO_DURATION_SECONDS` | 900 (15 min) | CPU time on 2 OCPU |
| `MAX_TARGET_CLIPS` | 4 | Faster turnaround |
| `CLEANUP_HOURS` | 24 | Saves block storage |

## 11. Troubleshooting

| Symptom | Check |
|---------|--------|
| 502 from nginx | `docker compose ps`; app listening on `127.0.0.1:8080` |
| Health `offline_whisper_model: false` | Run `prepare_offline.py` inside the container |
| Health `ffmpeg: false` | Rebuild image; FFmpeg must be in the Dockerfile |
| 413 on upload | Raise nginx `client_max_body_size` and `MAX_UPLOAD_SIZE_MB` together |
| Job stuck / SSE drops | Confirm nginx `proxy_buffering off` on stream path; increase `proxy_read_timeout` |
| OOM / killed workers | Set `MAX_CONCURRENT_WORKERS=1`; shorten max duration |

## 12. RazorHost + Oracle split (optional)

- **RazorHost:** marketing site, email, apex domain `example.com`
- **Oracle:** `app.example.com` or `clip.example.com` → this deployment

Same-origin UI is served by FastAPI at `/`; no separate frontend origin is required (`ALLOWED_ORIGINS` can stay empty).