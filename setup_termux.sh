#!/usr/bin/env bash
# Instala o Agente Orquestrador no Termux (Android) de forma automatizada.
# Uso: bash setup_termux.sh
set -eu

echo "==> Atualizando pacotes do Termux"
pkg update -y && pkg upgrade -y

echo "==> Instalando Python e ferramentas"
pkg install -y python python-pip git nano curl

echo "==> Instalando dependências do agente"
pip install flask requests beautifulsoup4 pytest

echo "==> Clonando o projeto (se ainda não existir)"
if [ ! -d "$HOME/agente-orquestrador" ]; then
  cd "$HOME"
  git clone https://github.com/SEU_USUARIO/agente-orquestrador.git
fi
cd "$HOME/agente-orquestrador"

echo "==> Criando .env (não commitável) — preencha com suas credenciais"
if [ ! -f .env ]; then
  cat > .env <<EOF
# COLE seu token do bot aqui (sem o prefixo bot)
TELEGRAM_BOT_TOKEN=
# Seu ID de chat (número)
TELEGRAM_CHAT_ID=
AE_MODO=teste
EOF
  chmod 600 .env
fi
echo "!!! Edite o arquivo .env e preencha TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID !!!"
echo "    (ex.: nano \$HOME/agente-orquestrador/.env)"

echo "==> Testando a instalação"
python3 -m pytest -q || echo "ATENÇÃO: algum teste falhou — revise."

echo ""
echo "Para iniciar o bot no Termux:"
echo "  cd \$HOME/agente-orquestrador"
echo "  ./run_bot.sh start"
echo ""
echo "Para ver logs: tail -f state/telegram_bot.log"
echo "Para manter rodando após fechar o Termux: use 'tmux' ou 'nohup' (já usado)."