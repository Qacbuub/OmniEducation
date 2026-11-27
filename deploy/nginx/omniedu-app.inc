# Shared by the HTTP and HTTPS server blocks in omniedu.conf.
root /usr/share/nginx/html;
client_max_body_size 12m;          # uploads: photos up to 3 MB, documents up to 10 MB
server_tokens off;

# Behind a tunnel (Tailscale Funnel) or Docker's port forwarding every visitor arrives from a private address.
# Trust the forwarded client address only from private networks, so rate limits apply per real visitor;
# a visitor connecting directly from the internet cannot fake it.
set_real_ip_from 127.0.0.0/8;
set_real_ip_from 10.0.0.0/8;
set_real_ip_from 172.16.0.0/12;
set_real_ip_from 192.168.0.0/16;
set_real_ip_from 100.64.0.0/10;    # Tailscale addresses
real_ip_header X-Forwarded-For;
real_ip_recursive on;

include /etc/nginx/conf.d/omniedu-headers.inc;

gzip on;
gzip_types text/css application/javascript application/json image/svg+xml;

location = /api/auth/login/ {
    limit_req zone=omniedu_login burst=5 nodelay;
    include /etc/nginx/conf.d/omniedu-proxy.inc;
}

location /api/ {
    include /etc/nginx/conf.d/omniedu-proxy.inc;
}

location /admin/ {
    include /etc/nginx/conf.d/omniedu-proxy.inc;
}

location /static/ {
    alias /srv/static/;
    expires 7d;
    access_log off;
}

location /media/tenant-logos/ {
    alias /srv/media/tenant-logos/;
    expires 1d;
}

location /media/ {
    return 404;  # private files go through the API only
}

# Built JS/CSS have content hashes in their names: cache them for a long time.
location /assets/ {
    expires 1y;
    add_header Cache-Control "public, immutable";
    include /etc/nginx/conf.d/omniedu-headers.inc;  # a location's add_header replaces the server's
    access_log off;
}

# Every other path is a React route: serve index.html and let the app handle it.
location / {
    try_files $uri /index.html;
    add_header Cache-Control "no-cache";
    include /etc/nginx/conf.d/omniedu-headers.inc;
}
