#!/bin/bash
# deploy.sh — 同步代码到 mbp 并在容器里执行；用法: ./deploy.sh [test|up|smoke|logs]
set -e
REMOTE_DIR='/Users/Administrator/Documents/02-Work/zhoushuang/zpassistant'
DOCKER='/Applications/Docker.app/Contents/Resources/bin/docker'
rsync -a --delete \
  --exclude .git --exclude .venv --exclude data --exclude .env \
  --exclude __pycache__ --exclude '*.pyc' --exclude .DS_Store \
  ./ "mbp:$REMOTE_DIR/"
run() { ssh mbp "export PATH=\"/Applications/Docker.app/Contents/Resources/bin:\$PATH\" && cd $REMOTE_DIR && $DOCKER compose $1"; }
case "${1:-up}" in
  test)  run "build -q" && run "run --rm app python -m pytest tests/ -q" ;;
  smoke) run "build -q" && run "run --rm app python scripts/smoke.py" ;;
  up)    run "build -q" && run "up -d" && echo 'http://100.127.149.33:8100' ;;
  logs)  run "logs --tail 100" ;;
esac
