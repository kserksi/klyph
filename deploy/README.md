# Deployment examples

These files are generic examples for self-hosting Klyph. Replace `fonts.example.com`, certificate paths, allowed origins, users, and installation paths before deploying.

## Files

- `nginx/klyph.conf.example`: HTTPS reverse proxy, rate limiting, and endpoint routing
- `systemd/font-service.service`: single-process Uvicorn service
- `logrotate.d/font-service`: daily rotation for structured application logs

## Application configuration

At minimum, set the public URL and the browser origins allowed to generate subsets:

```bash
FONT_PUBLIC_BASE_URL=https://fonts.example.com
FONT_ALLOWED_ORIGINS=https://www.example.com,https://status.example.com
```

`FONT_PUBLIC_BASE_URL` controls API font URLs and rendered SEO metadata. It is never inferred from an untrusted `Host` header.

## systemd

```bash
sudo useradd --system --uid 10001 --home-dir /opt/klyph fontsvc
sudo git clone https://github.com/kserksi/klyph /opt/klyph
cd /opt/klyph
sudo -u fontsvc python3 -m venv .venv
sudo -u fontsvc .venv/bin/pip install -r requirements.lock
sudo -u fontsvc .venv/bin/python scripts/download_fonts.py

sudo cp deploy/systemd/font-service.service /etc/systemd/system/
sudo cp deploy/logrotate.d/font-service /etc/logrotate.d/font-service
sudo systemctl daemon-reload
sudo systemctl enable --now font-service
```

Edit the environment values in the unit before starting it.

## Nginx

Define the rate-limit zone once inside the `http` block:

```nginx
limit_req_zone $binary_remote_addr zone=klyph_api:10m rate=20r/s;
```

Then copy and customize the site example:

```bash
sudo cp deploy/nginx/klyph.conf.example /etc/nginx/sites-available/klyph.conf
sudo ln -s /etc/nginx/sites-available/klyph.conf /etc/nginx/sites-enabled/klyph.conf
sudo nginx -t
sudo systemctl reload nginx
```

## Docker

```bash
python scripts/download_fonts.py
docker build -t klyph .
docker run -d --name klyph \
  -p 127.0.0.1:8000:8000 \
  -e FONT_PUBLIC_BASE_URL=https://fonts.example.com \
  -e FONT_ALLOWED_ORIGINS=https://www.example.com \
  -v font-cache:/app/cache \
  --restart unless-stopped \
  klyph
```

Verify the deployment with `/healthz` and `/readyz`. Place `/v2/fonts/*` behind a long-lived CDN cache, and apply per-client and global limits to `/v2/subsets`.
