#!/usr/bin/env bash
# Instala o Agente Orquestrador no Termux (Android) de forma automatizada.
# Uso: bash setup_termux.sh
#
# IMPORTANTE: o projeto ainda não tem repositório remoto. Antes de rodar este
# script, aponte a variável REPO abaixo para o seu repositório (ou rode
# `bash setup_termux.sh` já DENTRO do diretório do projeto clonado).
set -eu

# Edite para o seu repositório quando existir:
REPO="${AE_REPO:-https://github.com/SEU_USUARIO/agente-orquestrador.git}"

echo "==> Atualizando pacotes do Termux"
pkg update -y && pkg upgrade -y

echo "==> Instalando Python e ferramentas"
pkg install -y python python-pip git nano curl

echo "==> Instalando dependências do agente (requirements.txt)"
pip install --upgrade pip
if [ -d "$HOME/agente-orquestrador" ]; then
  cd "$HOME/agente-orquestrador"
else
  pip install flask requests beautifulsoup4
fi

echo "==> Obtendo o projeto"
if [ ! -d "$HOME/agente-orquestrador" ]; then
  if echo "$REPO" | grep -q "SEU_USUARIO"; then
    echo "!!! Ajuste a variável REPO (no topo deste script) para o seu repositório."
    echo "    Ou copie apenas os arquivos do projeto para $HOME/agente-orquestrador"
    exit 1
  fi
  cd "$HOME"
  git clone "$REPO" agente-orquestrador
fi
cd "$HOME/agente-orquestrador"

if [ -f requirements.txt ]; then
  pip install -r requirements.txt
fi

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