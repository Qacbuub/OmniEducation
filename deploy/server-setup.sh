#!/usr/bin/env bash
# Sets up (or updates) OmniEducation on an Ubuntu 22.04 / 24.04 server: Docker, swap, firewall,
# a free HTTPS certificate, PostgreSQL + Django + Nginx/React, and the demo data on first start.
#
# First time, as root, from a clone of the repository:
#     git clone https://github.com/Qacbuub/OmniEducation.git /opt/omniedu
#     bash /opt/omniedu/deploy/server-setup.sh
# Update later:
#     cd /opt/omniedu && git pull && sudo bash deploy/server-setup.sh
#
# Optional environment variables:
#     DOMAIN=demo.example.com   use your own domain (its DNS must point at this server).
#                               Without it the address is <ip-with-dashes>.sslip.io
#     PUBLIC_IP=1.2.3.4         skip looking the public address up
#
# Secrets are generated once into .env.prod (never committed); later runs keep them, and keep any
# lines you add there yourself (for example real email settings).
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"
export DEBIAN_FRONTEND=noninteractive
log() { echo "[$(date '+%H:%M:%S')] $*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this as root: sudo bash deploy/server-setup.sh" >&2
  exit 1
fi

# ---------------------------------------------------------------- 1. swap (small 1 GB servers)
if ! swapon --show | grep -q .; then
  log "Adding 2 GB of swap"
  fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ---------------------------------------------------------------- 2. packages
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1 || ! command -v certbot >/dev/null; then
  log "Installing Docker, Git and Certbot"
  apt-get update -q
  apt-get install -y -q git curl openssl certbot ca-certificates
  if ! apt-get install -y -q docker.io docker-compose-v2; then
    log "Ubuntu's Docker packages were not available; using Docker's installer"
    curl -fsSL https://get.docker.com | sh
  fi
  systemctl enable --now docker
fi

# ---------------------------------------------------------------- 3. firewall (Oracle images block 80/443)
if command -v iptables >/dev/null && iptables -S INPUT 2>/dev/null | grep -q -- '-j REJECT'; then
  for port in 80 443; do
    iptables -C INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null \
      || iptables -I INPUT 1 -p tcp --dport "$port" -m state --state NEW -j ACCEPT
  done
  command -v netfilter-persistent >/dev/null && netfilter-persistent save >/dev/null 2>&1 || true
  log "Opened ports 80 and 443 in the server firewall"
fi
if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null && ufw allow 443/tcp >/dev/null
fi

# ---------------------------------------------------------------- 4. address
IP="${PUBLIC_IP:-$(curl -fs4 --max-time 10 https://api.ipify.org || curl -fs4 --max-time 10 https://ifconfig.me || true)}"
if [ -z "$IP" ]; then
  echo "Could not find this server's public IP address. Run again with PUBLIC_IP=x.x.x.x" >&2
  exit 1
fi
HOST="${DOMAIN:-${IP//./-}.sslip.io}"
log "Public address: $IP  ->  $HOST"

COMPOSE=(docker compose -f docker-compose.prod.yml -f docker-compose.server.yml --env-file .env.prod)

# ---------------------------------------------------------------- 5. HTTPS certificate (Let's Encrypt)
CERT_DIR="/etc/letsencrypt/live/$HOST"
if [ ! -f "$CERT_DIR/fullchain.pem" ]; then
  log "Requesting a free HTTPS certificate for $HOST"
  # Port 80 must be free for the check: stop the web container if it is running.
  [ -f docker-compose.server.yml ] && [ -f .env.prod ] && "${COMPOSE[@]}" stop web >/dev/null 2>&1 || true
  # A few tries: on Oracle Cloud the ports may still be closed in the cloud firewall right after creation.
  # (Let's Encrypt allows 5 failed checks per address per hour, so stay under that.)
  for attempt in 1 2 3 4; do
    if certbot certonly --standalone --non-interactive --agree-tos --register-unsafely-without-email -d "$HOST"; then
      break
    fi
    if [ "$attempt" -lt 4 ]; then
      log "Certificate check failed (is TCP port 80 open in the cloud firewall?). Trying again in 3 minutes."
      sleep 180
    fi
  done
  [ -f "$CERT_DIR/fullchain.pem" ] \
    || log "WARNING: no certificate; the site runs on plain HTTP for now. Open ports 80/443 and run this script again."
fi
mkdir -p /etc/letsencrypt/renewal-hooks/pre /etc/letsencrypt/renewal-hooks/post
cat > /etc/letsencrypt/renewal-hooks/pre/omniedu.sh <<EOF
#!/bin/sh
cd "$APP_DIR" && docker compose -f docker-compose.prod.yml -f docker-compose.server.yml --env-file .env.prod stop web
EOF
cat > /etc/letsencrypt/renewal-hooks/post/omniedu.sh <<EOF
#!/bin/sh
cd "$APP_DIR" && docker compose -f docker-compose.prod.yml -f docker-compose.server.yml --env-file .env.prod start web
EOF
chmod +x /etc/letsencrypt/renewal-hooks/pre/omniedu.sh /etc/letsencrypt/renewal-hooks/post/omniedu.sh

if [ -f "$CERT_DIR/fullchain.pem" ]; then SCHEME=https; else SCHEME=http; fi
URL="$SCHEME://$HOST"

# ---------------------------------------------------------------- 6. settings (.env.prod)
if [ ! -f .env.prod ]; then
  log "Creating .env.prod with new random secrets"
  cp .env.prod.example .env.prod
  chmod 600 .env.prod
  set_once=1
else
  set_once=0
fi
setkey() {  # setkey NAME VALUE  -> replace the line or add it
  local key="$1" value="$2"
  if grep -q "^${key}=" .env.prod; then
    local escaped
    escaped=$(printf '%s' "$value" | sed -e 's/[\/&|]/\\&/g')
    sed -i "s|^${key}=.*|${key}=${escaped}|" .env.prod
  else
    printf '%s=%s\n' "$key" "$value" >> .env.prod
  fi
}
if [ "$set_once" = 1 ]; then
  setkey POSTGRES_PASSWORD "$(openssl rand -hex 24)"
  setkey DJANGO_SECRET_KEY "$(openssl rand -base64 60 | tr -d '\n/+=')"
  setkey SEED_DEMO true
fi
setkey DJANGO_ALLOWED_HOSTS "$HOST,$IP,localhost,127.0.0.1"
setkey FRONTEND_URL "$URL"
setkey CORS_ALLOWED_ORIGINS "$URL"
setkey DJANGO_CSRF_TRUSTED_ORIGINS "$URL"
if [ "$SCHEME" = https ]; then
  setkey DJANGO_SECURE_SSL_REDIRECT true
  setkey DJANGO_SECURE_COOKIES true
else
  setkey DJANGO_SECURE_SSL_REDIRECT false
  setkey DJANGO_SECURE_COOKIES false
fi

# ---------------------------------------------------------------- 7. Nginx config for this server
GEN="deploy/server-nginx"
mkdir -p "$GEN"
cp deploy/nginx/*.inc "$GEN/"
if [ "$SCHEME" = https ]; then
  # Browsers remember to use HTTPS for this address (sent on every response, also from locations).
  echo 'add_header Strict-Transport-Security "max-age=2592000" always;' >> "$GEN/omniedu-headers.inc"
  cat > "$GEN/omniedu.conf" <<EOF
# Generated by deploy/server-setup.sh - edit deploy/nginx/ instead and run the script again.
upstream omniedu_api {
    server backend:8000;
}
limit_req_zone \$binary_remote_addr zone=omniedu_login:10m rate=10r/m;

server {
    listen 80;
    server_name _;
    server_tokens off;
    location / {
        return 301 https://$HOST\$request_uri;
    }
}

server {
    listen 443 ssl;
    http2 on;
    server_name $HOST;
    ssl_certificate     /etc/letsencrypt/live/$HOST/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$HOST/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:omniedu_ssl:10m;
    include /etc/nginx/conf.d/omniedu-app.inc;
}
EOF
else
  cp deploy/nginx/omniedu.conf "$GEN/omniedu.conf"
fi
cat > docker-compose.server.yml <<'EOF'
# Generated by deploy/server-setup.sh: this server's Nginx config and HTTPS certificates.
services:
  web:
    volumes:
      - ./deploy/server-nginx:/etc/nginx/conf.d:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
EOF

# ---------------------------------------------------------------- 8. build and start
log "Building and starting the containers (the first build takes 5-15 minutes)"
"${COMPOSE[@]}" up -d --build --remove-orphans
"${COMPOSE[@]}" restart web >/dev/null   # pick up a changed Nginx config on updates

log "Waiting for the API (the first start also loads the demo data)"
for _ in $(seq 1 120); do
  code=$(curl -sk -o /dev/null -w '%{http_code}' --resolve "$HOST:443:127.0.0.1" --resolve "$HOST:80:127.0.0.1" \
         "$URL/api/auth/me/" || true)
  if [ "$code" = 401 ] || [ "$code" = 200 ]; then
    docker image prune -f >/dev/null 2>&1 || true
    log "READY: $URL"
    log "Demo sign-ins are listed in README.md (password Demo@1234)."
    exit 0
  fi
  sleep 10
done
log "The API did not answer within 20 minutes. Recent backend log:"
"${COMPOSE[@]}" logs --tail 60 backend
exit 1
