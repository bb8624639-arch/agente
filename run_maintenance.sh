#!/usr/bin/env bash
# Serviço persistente do agente de manutenção contínua (Agente Orquestrador).
# Executa o ciclo de manutenção a cada AE_MAINT_INTERVALO segundos (default 1800 = 30 min),
# reiniciando o ciclo se travar. USO: ./run_maintenance.sh [start|stop|restart|status]
set -u

PROJ="$(cd "$(dirname "$0")" && pwd)"
LOCK="$PROJ/state/maintenance.pid"
LOG="$PROJ/state/maintenance.log"
INTERVALO="${AE_MAINT_INTERVALO:-1800}"

cd "$PROJ"
mkdir -p state

start() {
  if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
    echo "Manutenção já rodando (PID $(cat "$LOCK"))."
    return 0
  fi
  nohup bash -c '
    while true; do
      python3 -m autoexpand.maintenance --ciclo >> "'"$LOG"'" 2>&1
      printf "[%s] ciclo de manutenção concluído; próximo em %ss\n" \
        "$(date "+%Y-%m-%d %H:%M:%S")" "'"$INTERVALO"'" >> "'"$LOG"'"
      sleep "'"$INTERVALO"'"
    done
  ' >> /dev/null 2>&1 &
  echo $! > "$LOCK"
  echo "Manutenção iniciada (intervalo ${INTERVALO}s). PID $(cat "$LOCK"). Log: $LOG"
}

stop() {
  local pid
  if [ -f "$LOCK" ]; then
    pid="$(cat "$LOCK")"
    pkill -P "$pid" 2>/dev/null
    kill "$pid" 2>/dev/null
    rm -f "$LOCK"
    pkill -f "autoexpand.maintenance" 2>/dev/null
    echo "Manutenção parada."
  else
    echo "Sem PID registrado."
    pkill -f "autoexpand.maintenance" 2>/dev/null
  fi
}

status() {
  if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
    echo "Manutenção ATIVA (wrapper PID $(cat "$LOCK")), intervalo ${INTERVALO}s."
    ps aux | grep "autoexpand.maintenance" | grep -v grep
  else
    echo "Manutenção INATIVA."
  fi
}

case "${1:-}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; sleep 1; start ;;
  status)  status ;;
  *) echo "Uso: $0 {start|stop|restart|status}"; exit 1 ;;
esac