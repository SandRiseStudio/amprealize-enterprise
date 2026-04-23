#!/bin/sh
# =============================================================================
# entrypoint.prod.sh — Amprealize API container (Fly.io production)
# =============================================================================
# Prepares the runtime environment and hands off to supervisord, which
# manages both nginx and uvicorn.  Runs as root so nginx can bind :8080
# and write its pid file; uvicorn is dropped to the amprealize user by
# the [program:uvicorn] user= directive in supervisord.conf.
# =============================================================================

set -e

echo "=== Amprealize API (prod) startup ==="

# Ensure directories that nginx / supervisord need exist.
# These may be absent in a minimal Debian slim image.
mkdir -p /var/log/nginx /var/log/supervisor /run

# Validate nginx config before starting supervisord.
# Catches config errors early so the container exits with a clear message
# rather than nginx silently failing inside supervisord.
echo "Validating nginx config..."
nginx -t -c /etc/nginx/nginx.conf

echo "Starting supervisord (nginx + uvicorn)..."
exec /usr/bin/supervisord -c /etc/supervisord.conf
