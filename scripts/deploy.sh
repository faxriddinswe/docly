#!/usr/bin/env bash
# Deploy Docly to ONE shared VPS behind the shared edge Caddy (see docs/DEPLOY.md).
#   scripts/deploy.sh            deploy (needs .env.deploy)
#   DRY_RUN=1 scripts/deploy.sh  print every remote command instead of running it
# Safety: only touches /opt/docly, the compose project "docly", /opt/edge/sites/docly.caddy, and creates /opt/edge ONLY
# if it does not exist and ports 80/443 are free. Never stops/removes anything it did not create.
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_DEPLOY_FILE:-.env.deploy}"
if [ ! -f "$ENV_FILE" ]; then
  echo "No $ENV_FILE: nothing deployed. Images can still be built (docker build). See docs/BLOCKERS.md B3." >&2
  exit 3
fi
# shellcheck disable=SC1090
. "$ENV_FILE"
for v in DEPLOY_HOST DEPLOY_USER SSH_KEY_PATH BASE_DOMAIN SUBDOMAIN; do
  [ -n "${!v:-}" ] || { echo "$v missing in $ENV_FILE" >&2; exit 2; }
done
SSH_KEY_PATH="${SSH_KEY_PATH/#\~/$HOME}"
HOST="$SUBDOMAIN.$BASE_DOMAIN"
TAG="$(git rev-parse --short HEAD 2>/dev/null || date +%s)"
REMOTE=/opt/docly
DRY="${DRY_RUN:-0}"

SSH_OPTS=(-i "$SSH_KEY_PATH" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
remote() { # run a command on the server
  if [ "$DRY" = 1 ]; then echo "[dry-run remote] $*"; else ssh "${SSH_OPTS[@]}" "$DEPLOY_USER@$DEPLOY_HOST" "$@"; fi
}
copy() { # copy local file -> remote path
  if [ "$DRY" = 1 ]; then echo "[dry-run copy] $1 -> $2"; else scp "${SSH_OPTS[@]}" -q "$1" "$DEPLOY_USER@$DEPLOY_HOST:$2"; fi
}
say() { printf '\n== %s\n' "$*"; }

say "1/8 Preflight (read-only) on $DEPLOY_HOST"
remote 'set -e
  docker version --format "docker {{.Server.Version}}" && docker compose version --short
  echo "disk free on /opt: $(df -h /opt | awk "NR==2{print \$4}")   (need >= 3G)"
  echo "mem available: $(awk "/MemAvailable/{printf \"%d MB\", \$2/1024}" /proc/meminfo)   (need >= 600 MB)"
  echo "listeners on 80/443:"; (ss -ltnH "( sport = :80 or sport = :443 )" || true) | awk "{print \"  \" \$4}"
  docker network inspect edge >/dev/null 2>&1 && echo "edge network: present" || echo "edge network: ABSENT"
  test -f /opt/edge/Caddyfile && echo "/opt/edge/Caddyfile: present" || echo "/opt/edge/Caddyfile: ABSENT"'

say "2/8 Ensure shared edge Caddy"
remote 'set -e
  if docker network inspect edge >/dev/null 2>&1 && test -f /opt/edge/Caddyfile; then echo "edge exists: reusing"; exit 0; fi
  if ss -ltnH "( sport = :80 or sport = :443 )" | grep -q .; then
    echo "ERROR: ports 80/443 are in use by something that is not the edge Caddy. Refusing to touch it (needs the owner)." >&2; exit 42; fi
  test -w /opt || { echo "ERROR: /opt not writable by $(id -un); creating the edge needs root. Ask the owner (see docs/DEPLOY.md)." >&2; exit 43; }
  mkdir -p /opt/edge/sites && cd /opt/edge
  printf "{\n\temail admin@%s\n}\nimport /etc/caddy/sites/*.caddy\n" "'"$BASE_DOMAIN"'" > Caddyfile
  cat > docker-compose.yml <<YML
name: edge
services:
  caddy:
    image: caddy:2-alpine
    container_name: edge-caddy
    restart: unless-stopped
    ports: ["80:80", "443:443", "443:443/udp"]
    volumes: ["./Caddyfile:/etc/caddy/Caddyfile:ro", "./sites:/etc/caddy/sites:ro", "caddy_data:/data", "caddy_config:/config"]
    networks: [edge]
    mem_limit: 96m
networks: {edge: {name: edge}}
volumes: {caddy_data: {}, caddy_config: {}}
YML
  docker compose up -d && echo "edge created"'

say "3/8 Build images (tag $TAG)"
if [ "${SKIP_BUILD:-0}" = 1 ]; then echo "SKIP_BUILD=1"; else
  docker build -t "docly-api:$TAG" backend
  docker build -t "docly-web:$TAG" --build-arg "NEXT_PUBLIC_API_URL=https://$HOST/api" frontend
fi

say "4/8 Ship images (docker save | ssh docker load); keep previous tag for rollback"
remote 'for i in docly-api docly-web; do docker image inspect $i:latest >/dev/null 2>&1 && docker tag $i:latest $i:prev || true; done'
if [ "$DRY" = 1 ]; then echo "[dry-run] docker save docly-api:$TAG docly-web:$TAG | gzip | ssh ... 'gunzip | docker load'"; else
  docker save "docly-api:$TAG" "docly-web:$TAG" | gzip | ssh "${SSH_OPTS[@]}" "$DEPLOY_USER@$DEPLOY_HOST" 'gunzip | docker load'
fi
remote "docker tag docly-api:$TAG docly-api:latest && docker tag docly-web:$TAG docly-web:latest"

say "5/8 Files + secrets (generated once, kept on the server only)"
remote "mkdir -p $REMOTE"
copy deploy/docker-compose.prod.yml "$REMOTE/docker-compose.prod.yml"
copy deploy/backup.sh "$REMOTE/backup.sh"
remote "set -e; cd $REMOTE
  if [ ! -f .env.prod ]; then
    umask 077
    { echo DOCLY_HOST=$HOST
      echo POSTGRES_PASSWORD=\$(openssl rand -hex 16)
      echo APP_DB_PASSWORD=\$(openssl rand -hex 16)
      echo JWT_SECRET=\$(openssl rand -hex 32)
      echo OTP_SENDER=eskiz; echo ESKIZ_EMAIL=; echo ESKIZ_PASSWORD=
      echo TELEGRAM_BOT_TOKEN=; echo TELEGRAM_BOT_USERNAME=; } > .env.prod
    echo 'created .env.prod with fresh secrets (fill ESKIZ_*/TELEGRAM_* later; see BLOCKERS)'
  else sed -i 's/^DOCLY_HOST=.*/DOCLY_HOST=$HOST/' .env.prod; fi"

say "6/8 Start stack"
remote "set -e; cd $REMOTE
  PROFILES=''; grep -q '^TELEGRAM_BOT_TOKEN=.\\+' .env.prod && PROFILES='--profile telegram'
  IMAGE_TAG=latest COMPOSE_PROJECT_NAME=docly docker compose --env-file .env.prod -f docker-compose.prod.yml \$PROFILES up -d --remove-orphans
  for i in \$(seq 1 60); do
    n=\$(docker ps --filter label=com.docker.compose.project=docly --filter health=starting -q | wc -l); [ \"\$n\" = 0 ] && break; sleep 2; done
  docker compose -p docly -f docker-compose.prod.yml ps --format 'table {{.Service}}\t{{.Status}}'"

say "7/8 Edge snippet (validate before reload)"
SNIPPET="$(sed "s/__DOCLY_HOST__/$HOST/" deploy/docly.caddy)"
if [ "$DRY" = 1 ]; then
  echo "[dry-run] would install /opt/edge/sites/docly.caddy:"; echo "$SNIPPET" | sed 's/^/    /'
else
  TMP="$(mktemp)"; printf '%s\n' "$SNIPPET" > "$TMP"
  copy "$TMP" /tmp/docly.caddy.new; rm -f "$TMP"
fi
remote 'set -e
  # find the Caddy container attached to the shared edge network (do not assume its name)
  EDGE=$(docker ps --filter network=edge --format "{{.Names}} {{.Image}}" | awk "\$2 ~ /caddy/ {print \$1; exit}")
  test -n "$EDGE" || { echo "ERROR: no running caddy container on network edge" >&2; exit 45; }
  mkdir -p /opt/edge/sites
  test -f /opt/edge/sites/docly.caddy && cp /opt/edge/sites/docly.caddy /tmp/docly.caddy.bak || true
  cp /tmp/docly.caddy.new /opt/edge/sites/docly.caddy
  if docker exec "$EDGE" caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
    docker exec "$EDGE" caddy reload --config /etc/caddy/Caddyfile && echo "caddy ($EDGE) reloaded"
  else
    echo "ERROR: caddy config invalid; reverting our snippet only" >&2
    if test -f /tmp/docly.caddy.bak; then cp /tmp/docly.caddy.bak /opt/edge/sites/docly.caddy; else rm -f /opt/edge/sites/docly.caddy; fi
    exit 44
  fi'

say "8/8 Smoke test https://$HOST"
if [ "$DRY" = 1 ]; then echo "[dry-run] scripts/smoke.sh https://$HOST"; exit 0; fi
for i in $(seq 1 12); do curl -fsS -o /dev/null "https://$HOST/api/health" 2>/dev/null && break; sleep 5; done  # TLS issuance can take a moment
if scripts/smoke.sh "https://$HOST"; then echo "DEPLOY OK: https://$HOST (tag $TAG)"; else
  echo "SMOKE FAILED -> rolling back to previous images" >&2
  remote "cd $REMOTE && docker image inspect docly-api:prev >/dev/null 2>&1 && IMAGE_TAG=prev COMPOSE_PROJECT_NAME=docly docker compose --env-file .env.prod -f docker-compose.prod.yml up -d || echo 'no previous image to roll back to'"
  exit 1
fi
