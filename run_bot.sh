#!/usr/bin/env bash
# Serviço persistente do bot Telegram do Agente Orquestrador.
# Reinicia o bot automaticamente se ele cair (loop com backoff).
# USO: ./run_bot.sh [start|stop|restart|status]
set -u

PROJ="$(cd "$(dirname "$0")" && pwd)"
LOCK="$PROJ/state/telegram_bot.pid"
LOG="$PROJ/state/telegram_bot.log"
PYTHON="${PYTHON:-python3}"

cd "$PROJ"
mkdir -p state

start() {
  if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
    echo "Bot já rodando (PID $(cat "$LOCK"))."
    return 0
  fi
  nohup bash -c '
    contador=0
    while true; do
      python3 -m autoexpand.telegram.bot >> "'"$LOG"'" 2>&1
      codigo=$?
      contador=$((contador+1))
      printf "[%s] bot caiu (código %s), tentativa %s; reiniciando em 3s\n" \
        "$(date "+%Y-%m-%d %H:%M:%S")" "$codigo" "$contador" >> "'"$LOG"'"
      sleep 3
    done
  ' >> /dev/null 2>&1 &
  echo $! > "$LOCK"
  echo "Bot iniciado (PID $(cat "$LOCK")). Log: $LOG"
}

stop() {
  local pid
  if [ -f "$LOCK" ]; then
    pid="$(cat "$LOCK")"
    # mata o wrapper e filhos (o python do bot)
    pkill -P "$pid" 2>/dev/null
    kill "$pid" 2>/dev/null
    rm -f "$LOCK"
    # garante que nenhum processo do bot ficou vivo
    pkill -f "autoexpand.telegram.bot" 2>/dev/null
    echo "Bot parado."
  else
    echo "Sem PID registrado."
    pkill -f "autoexpand.telegram.bot" 2>/dev/null
  fi
}

status() {
  if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
    echo "Bot ATIVO (wrapper PID $(cat "$LOCK"))."
    ps aux | grep -E "autoexpand.telegram.bot" | grep -v grep
  else
    echo "Bot INATIVO (nenhum processo do bot rodando)."
  fi
}

case "${1:-}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; sleep 1; start ;;
  status)  status ;;
  *) echo "Uso: $0 {start|stop|restart|status}"; exit 1 ;;
esac