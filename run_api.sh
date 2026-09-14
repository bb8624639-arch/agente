#!/usr/bin/env bash
# Serviço persistente da API do painel (Agente Orquestrador).
# Auto-restart se cair. Porta via AE_API_PORT (default 8080).
# USO: ./run_api.sh [start|stop|restart|status]
set -u

PROJ="$(cd "$(dirname "$0")" && pwd)"
LOCK="$PROJ/state/api.pid"
LOG="$PROJ/state/api.log"
API_TOKEN="${AE_API_TOKEN:-}"
PORT="${AE_API_PORT:-8080}"

cd "$PROJ"
mkdir -p state

start() {
  if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
    echo "API já rodando (PID $(cat "$LOCK"))."
    return 0
  fi
  local cmd="python3 -m autoexpand.web.api"
  nohup bash -c '
    while true; do
      AE_API_TOKEN="'"$API_TOKEN"'" AE_API_PORT="'"$PORT"'" python3 -m autoexpand.web.api >> "'"$LOG"'" 2>&1
      printf "[%s] API caiu (código %s); reiniciando em 3s\n" \
        "$(date "+%Y-%m-%d %H:%M:%S")" "$?" >> "'"$LOG"'"
      sleep 3
    done
  ' >> /dev/null 2>&1 &
  echo $! > "$LOCK"
  echo "API iniciada na porta ${PORT}. PID $(cat "$LOCK"). Log: $LOG"
}

stop() {
  local pid
  if [ -f "$LOCK" ]; then
    pid="$(cat "$LOCK")"
    pkill -P "$pid" 2>/dev/null
    kill "$pid" 2>/dev/null
    rm -f "$LOCK"
    pkill -f "autoexpand.web.api" 2>/dev/null
    echo "API parada."
  else
    echo "Sem PID registrado."
    pkill -f "autoexpand.web.api" 2>/dev/null
  fi
}

status() {
  if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
    echo "API ATIVA (wrapper PID $(cat "$LOCK"))."
    ps aux | grep "autoexpand.web.api" | grep -v grep
  else
    echo "API INATIVA."
  fi
}

case "${1:-}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; sleep 1; start ;;
  status)  status ;;
  *) echo "Uso: $0 {start|stop|restart|status}"; exit 1 ;;
esac