#!/usr/bin/env bash
# Orquestra todos os serviços persistentes do Agente Orquestrador:
#   bot Telegram   -> run_bot.sh
#   API do painel  -> run_api.sh
#   manutenção     -> run_maintenance.sh
# USO: ./servicos.sh {start|stop|restart|status}
set -u

PROJ="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJ"

case "${1:-}" in
  start)
    echo "### Bot Telegram";   ./run_bot.sh start
    echo "### API painel";     AE_API_PORT="${AE_API_PORT:-8080}" ./run_api.sh start
    echo "### Manutenção";     AE_MAINT_INTERVALO="${AE_MAINT_INTERVALO:-1800}" ./run_maintenance.sh start
    ;;
  stop)
    echo "### Bot Telegram";   ./run_bot.sh stop
    echo "### API painel";     ./run_api.sh stop
    echo "### Manutenção";     ./run_maintenance.sh stop
    ;;
  restart)
    "$0" stop; sleep 1; "$0" start
    ;;
  status)
    ./run_bot.sh status | head -1
    ./run_api.sh status | head -1
    ./run_maintenance.sh status | head -1
    ;;
  *) echo "Uso: $0 {start|stop|restart|status}"; exit 1 ;;
esac