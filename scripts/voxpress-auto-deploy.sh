#!/usr/bin/env bash
set -euo pipefail

LOCK_FILE="/tmp/voxpress-auto-deploy.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[voxpress-auto-deploy] another run is in progress"
  exit 0
fi

RUN_USER="work"
REPO_URL="https://github.com/weekdmond/voxpress.git"
SOURCE_ROOT="/home/work/deploy-src/voxpress"
RUNTIME_ROOT="/home/work/app"
BACKEND_DIR="$RUNTIME_ROOT/voxpress-api"
FRONTEND_DIR="$RUNTIME_ROOT/voxpress"
WEB_DIST_DIR="/var/www/voxpress-web"
BACKEND_RUNTIME_VENV="$BACKEND_DIR/.venv"
DEPLOY_INFO_PATH="$BACKEND_DIR/.deploy-info.json"
BRANCH="main"
FORCE_DEPLOY="${1:-}"

log() {
  printf '[voxpress-auto-deploy] %s\n' "$*"
}

as_work() {
  sudo -u "$RUN_USER" "$@"
}

ensure_source_clone() {
  if [[ -d "$SOURCE_ROOT/.git" ]]; then
    return
  fi
  log "bootstrapping source clone at $SOURCE_ROOT"
  install -d -o "$RUN_USER" -g "$RUN_USER" "$(dirname "$SOURCE_ROOT")"
  as_work git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$SOURCE_ROOT"
}

ensure_frontend_build_env() {
  cat > "$SOURCE_ROOT/voxpress/.env.production" <<'EOF'
VITE_API_BASE=https://app.speechfolio.com
VITE_SSE_BASE=https://app.speechfolio.com
VITE_USE_MOCK=false
VITE_ENABLE_TWEAKS=false
EOF
}

cleanup_frontend_build_env() {
  rm -f "$SOURCE_ROOT/voxpress/.env.production"
}

write_deploy_info() {
  local commit short_commit version deployed_at
  commit=$(as_work git -C "$SOURCE_ROOT" rev-parse HEAD)
  short_commit=$(as_work git -C "$SOURCE_ROOT" rev-parse --short HEAD)
  version=$("$BACKEND_RUNTIME_VENV/bin/python" - <<'PY'
from voxpress import __version__
print(__version__)
PY
)
  deployed_at=$(date --iso-8601=seconds)
  cat > "$DEPLOY_INFO_PATH" <<EOF
{"version":"$version","commit":"$short_commit","branch":"$BRANCH","deployed_at":"$deployed_at","source_commit":"$commit"}
EOF
  chown "$RUN_USER:$RUN_USER" "$DEPLOY_INFO_PATH"
}

sync_backend() {
  log "sync backend runtime"
  rsync -az --delete \
    --exclude='.env' --exclude='.env.local' --exclude='.venv/' \
    --exclude='__pycache__' --exclude='.pytest_cache/' --exclude='.ruff_cache/' \
    --exclude='.DS_Store' --exclude='logs/' \
    "$SOURCE_ROOT/voxpress-api/" "$BACKEND_DIR/"
  chown -R "$RUN_USER:$RUN_USER" "$BACKEND_DIR"
}

build_and_sync_frontend() {
  log "build frontend"
  ensure_frontend_build_env
  trap cleanup_frontend_build_env EXIT
  as_work bash -lc "cd '$SOURCE_ROOT/voxpress' && npm ci && npm run build"
  log "sync frontend dist"
  rsync -az --delete "$SOURCE_ROOT/voxpress/dist/" "$WEB_DIST_DIR/"
  chown -R "$RUN_USER:$RUN_USER" "$WEB_DIST_DIR"
  cleanup_frontend_build_env
  trap - EXIT
}

install_backend_deps() {
  log "install backend deps"
  as_work "$BACKEND_RUNTIME_VENV/bin/pip" install -q -e "$BACKEND_DIR"
  log "run migrations"
  as_work bash -lc "cd '$BACKEND_DIR' && .venv/bin/alembic upgrade head"
}

restart_services() {
  log "restart services"
  systemctl restart voxpress-api voxpress-worker
  systemctl is-active --quiet voxpress-api
  systemctl is-active --quiet voxpress-worker
}

main() {
  ensure_source_clone
  local local_head remote_head
  local_head=$(as_work git -C "$SOURCE_ROOT" rev-parse HEAD)
  as_work git -C "$SOURCE_ROOT" fetch origin "$BRANCH" --quiet
  remote_head=$(as_work git -C "$SOURCE_ROOT" rev-parse "origin/$BRANCH")
  if [[ "$FORCE_DEPLOY" != "--force" && -f "$DEPLOY_INFO_PATH" && "$local_head" == "$remote_head" ]]; then
    log "no updates on $BRANCH"
    exit 0
  fi

  log "update detected: $local_head -> $remote_head"
  as_work git -C "$SOURCE_ROOT" checkout "$BRANCH"
  as_work git -C "$SOURCE_ROOT" reset --hard "origin/$BRANCH"
  as_work git -C "$SOURCE_ROOT" clean -fd

  build_and_sync_frontend
  sync_backend
  install_backend_deps
  write_deploy_info
  restart_services
  log "deploy complete"
}

main "$@"
